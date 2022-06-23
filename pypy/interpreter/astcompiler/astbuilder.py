from pypy.interpreter.astcompiler import ast, consts, misc
from pypy.interpreter.astcompiler.ast import build
from pypy.interpreter.astcompiler import asthelpers # Side effects
from pypy.interpreter.astcompiler import fstring
from pypy.interpreter import error
from pypy.interpreter.pyparser.pygram import syms, tokens
from pypy.interpreter.pyparser.error import SyntaxError
from rpython.rlib.objectmodel import always_inline, we_are_translated, specialize


def ast_from_node(space, node, compile_info, recursive_parser=None):
    """Turn a parse tree, node, to AST."""
    ast = ASTBuilder(space, node, compile_info, recursive_parser).build_ast()
    #
    # When we are not translated, we send this ast to validate_ast.
    # The goal is to check that validate_ast doesn't crash on valid
    # asts, at least.
    if not we_are_translated():
        from pypy.interpreter.astcompiler import validate
        validate.validate_ast(space, ast)
    return ast


augassign_operator_map = {
    '+='  : ast.Add,
    '-='  : ast.Sub,
    '/='  : ast.Div,
    '//=' : ast.FloorDiv,
    '%='  : ast.Mod,
    '@='  : ast.MatMult,
    '<<='  : ast.LShift,
    '>>='  : ast.RShift,
    '&='  : ast.BitAnd,
    '|='  : ast.BitOr,
    '^='  : ast.BitXor,
    '*='  : ast.Mult,
    '**=' : ast.Pow
}

operator_map = misc.dict_to_switch({
    tokens.VBAR : ast.BitOr,
    tokens.CIRCUMFLEX : ast.BitXor,
    tokens.AMPER : ast.BitAnd,
    tokens.LEFTSHIFT : ast.LShift,
    tokens.RIGHTSHIFT : ast.RShift,
    tokens.PLUS : ast.Add,
    tokens.MINUS : ast.Sub,
    tokens.STAR : ast.Mult,
    tokens.SLASH : ast.Div,
    tokens.DOUBLESLASH : ast.FloorDiv,
    tokens.PERCENT : ast.Mod,
    tokens.AT : ast.MatMult
})


class ASTBuilder(object):

    def __init__(self, space, n, compile_info, recursive_parser=None):
        self.space = space
        self.compile_info = compile_info
        self.root_node = n
        # used in f-strings and type_ignores
        self.recursive_parser = recursive_parser

    def build_ast(self):
        """Convert an top level parse tree node into an AST mod."""
        n = self.root_node
        if n.type == syms.file_input:
            stmts = []
            for i in range(n.num_children() - 1):
                stmt = n.get_child(i)
                if stmt.type == tokens.NEWLINE:
                    continue
                sub_stmts_count = self.number_of_statements(stmt)
                if sub_stmts_count == 1:
                    stmts.append(self.handle_stmt(stmt))
                else:
                    stmt = stmt.get_child(0)
                    for j in range(sub_stmts_count):
                        small_stmt = stmt.get_child(j * 2)
                        stmts.append(self.handle_stmt(small_stmt))
            type_ignores = []
            if self.recursive_parser is not None:
                for type_ignore in self.recursive_parser.type_ignores:
                    tag = self.space.newtext(type_ignore.value)
                    type_ignores.append(ast.TypeIgnore(type_ignore.lineno, tag))
            return ast.Module(stmts, type_ignores)
        elif n.type == syms.eval_input:
            body = self.handle_testlist(n.get_child(0))
            return ast.Expression(body)
        elif n.type == syms.single_input:
            first_child = n.get_child(0)
            if first_child.type == tokens.NEWLINE:
                # An empty line.
                return ast.Interactive([])
            else:
                num_stmts = self.number_of_statements(first_child)
                if num_stmts == 1:
                    stmts = [self.handle_stmt(first_child)]
                else:
                    stmts = []
                    for i in range(0, first_child.num_children(), 2):
                        stmt = first_child.get_child(i)
                        if stmt.type == tokens.NEWLINE:
                            break
                        stmts.append(self.handle_stmt(stmt))
                return ast.Interactive(stmts)
        elif n.type == syms.func_type_input:
            func = n.get_child(0)
            argtypes = []

            if func.get_child(1).type == syms.typelist:
                type_list = func.get_child(1)
                for i in range(type_list.num_children()):
                    current = type_list.get_child(i)
                    if current.type == syms.test:
                        argtypes.append(self.handle_expr(current))

            returns = self.handle_expr(func.get_child(-1))
            return ast.FunctionType(argtypes, returns)
        else:
            raise AssertionError("unknown root node")

    def number_of_statements(self, n):
        """Compute the number of AST statements contained in a node."""
        stmt_type = n.type
        if stmt_type == syms.compound_stmt:
            return 1
        elif stmt_type == syms.stmt:
            return self.number_of_statements(n.get_child(0))
        elif stmt_type == syms.simple_stmt:
            # Divide to remove semi-colons.
            return n.num_children() // 2
        else:
            raise AssertionError("non-statement node")

    def error(self, msg, n):
        """Raise a SyntaxError with the lineno and column set to n's."""
        raise SyntaxError(msg, n.get_lineno(), n.get_column(),
                          filename=self.compile_info.filename,
                          text=n.get_line())

    def error_ast(self, msg, ast_node):
        raise SyntaxError(msg, ast_node.lineno, ast_node.col_offset,
                          filename=self.compile_info.filename)

    def check_feature(self, condition, version, msg, n):
        if condition and self.compile_info.feature_version < version:
            return self.error(msg, n)

    def deprecation_warn(self, msg, n):
        from pypy.module._warnings.interp_warnings import warn_explicit
        space = self.space
        try:
            warn_explicit(
                space, space.newtext(msg),
                space.w_DeprecationWarning,
                space.newtext(self.compile_info.filename),
                n.get_lineno(),
                space.w_None,
                space.w_None,
                space.w_None,
                space.w_None,
                )
        except error.OperationError as e:
            if e.match(space, space.w_DeprecationWarning):
                self.error(msg, n)
            else:
                raise

    def check_forbidden_name(self, name, node):
        try:
            misc.check_forbidden_name(self.space, name)
        except misc.ForbiddenNameAssignment as e:
            self.error("cannot assign to %s" % (e.name,), node)

    def new_identifier(self, name):
        return misc.new_identifier(self.space, name)

    def set_context(self, expr, ctx):
        """Set the context of an expression to Store or Del if possible."""
        try:
            expr.set_context(self.space, ctx)
        except ast.UnacceptableExpressionContext as e:
            self.error_ast(e.msg, e.node)
        except misc.ForbiddenNameAssignment as e:
            self.error_ast("cannot assign to %s" % (e.name,), e.node)

    def handle_del_stmt(self, del_node):
        targets = self.handle_exprlist(del_node.get_child(1), ast.Del)
        return build(ast.Delete, targets, del_node)

    def handle_flow_stmt(self, flow_node):
        first_child = flow_node.get_child(0)
        first_child_type = first_child.type
        if first_child_type == syms.break_stmt:
            return build(ast.Break, flow_node)
        elif first_child_type == syms.continue_stmt:
            return build(ast.Continue, flow_node)
        elif first_child_type == syms.yield_stmt:
            yield_expr = self.handle_expr(first_child.get_child(0))
            return build(ast.Expr, yield_expr, flow_node)
        elif first_child_type == syms.return_stmt:
            if first_child.num_children() == 1:
                values = None
            else:
                values = self.handle_testlist(first_child.get_child(1))
            return build(ast.Return, values, flow_node)
        elif first_child_type == syms.raise_stmt:
            exc = None
            cause = None
            child_count = first_child.num_children()
            if child_count >= 2:
                exc = self.handle_expr(first_child.get_child(1))
            if child_count >= 4:
                cause = self.handle_expr(first_child.get_child(3))
            return build(ast.Raise, exc, cause, flow_node)
        else:
            raise AssertionError("unknown flow statement")

    def alias_for_import_name(self, import_name, store=True):
        while True:
            import_name_type = import_name.type
            if import_name_type == syms.import_as_name:
                name = self.new_identifier(import_name.get_child(0).get_value())
                if import_name.num_children() == 3:
                    as_name = self.new_identifier(
                        import_name.get_child(2).get_value())
                    self.check_forbidden_name(as_name, import_name.get_child(2))
                else:
                    as_name = None
                    self.check_forbidden_name(name, import_name.get_child(0))
                return ast.alias(name, as_name)
            elif import_name_type == syms.dotted_as_name:
                if import_name.num_children() == 1:
                    import_name = import_name.get_child(0)
                    continue
                alias = self.alias_for_import_name(import_name.get_child(0),
                                                   store=False)
                asname_node = import_name.get_child(2)
                alias.asname = self.new_identifier(asname_node.get_value())
                self.check_forbidden_name(alias.asname, asname_node)
                return alias
            elif import_name_type == syms.dotted_name:
                if import_name.num_children() == 1:
                    name = self.new_identifier(import_name.get_child(0).get_value())
                    if store:
                        self.check_forbidden_name(name, import_name.get_child(0))
                    return ast.alias(name, None)
                name_parts = [import_name.get_child(i).get_value()
                              for i in range(0, import_name.num_children(), 2)]
                name = ".".join(name_parts)
                return ast.alias(name, None)
            elif import_name_type == tokens.STAR:
                return ast.alias("*", None)
            else:
                raise AssertionError("unknown import name")

    def handle_import_stmt(self, import_node):
        import_node = import_node.get_child(0)
        if import_node.type == syms.import_name:
            dotted_as_names = import_node.get_child(1)
            aliases = [self.alias_for_import_name(dotted_as_names.get_child(i))
                       for i in range(0, dotted_as_names.num_children(), 2)]
            return build(ast.Import, aliases, import_node)
        elif import_node.type == syms.import_from:
            child_count = import_node.num_children()
            module = None
            modname = None
            i = 1
            dot_count = 0
            while i < child_count:
                child = import_node.get_child(i)
                child_type = child.type
                if child_type == syms.dotted_name:
                    module = self.alias_for_import_name(child, False)
                    i += 1
                    break
                elif child_type == tokens.ELLIPSIS:
                    # Special case for tokenization.
                    dot_count += 2
                elif child_type != tokens.DOT:
                    break
                i += 1
                dot_count += 1
            i += 1
            after_import_type = import_node.get_child(i).type
            star_import = False
            if after_import_type == tokens.STAR:
                names_node = import_node.get_child(i)
                star_import = True
            elif after_import_type == tokens.LPAR:
                names_node = import_node.get_child(i + 1)
            elif after_import_type == syms.import_as_names:
                names_node = import_node.get_child(i)
                if names_node.num_children() % 2 == 0:
                    self.error("trailing comma is only allowed with "
                               "surronding parenthesis", names_node)
            else:
                raise AssertionError("unknown import node")
            if star_import:
                aliases = [self.alias_for_import_name(names_node)]
            else:
                aliases = [self.alias_for_import_name(names_node.get_child(i))
                           for i in range(0, names_node.num_children(), 2)]
            if module is not None:
                modname = module.name
            return build(ast.ImportFrom, modname, aliases, dot_count, import_node)
        else:
            raise AssertionError("unknown import node")

    def handle_global_stmt(self, global_node):
        names = [self.new_identifier(global_node.get_child(i).get_value())
                 for i in range(1, global_node.num_children(), 2)]
        return build(ast.Global, names, global_node)

    def handle_nonlocal_stmt(self, nonlocal_node):
        names = [self.new_identifier(nonlocal_node.get_child(i).get_value())
                 for i in range(1, nonlocal_node.num_children(), 2)]
        return build(ast.Nonlocal, names, nonlocal_node)

    def handle_assert_stmt(self, assert_node):
        expr = self.handle_expr(assert_node.get_child(1))
        msg = None
        if assert_node.num_children() == 4:
            msg = self.handle_expr(assert_node.get_child(3))
        return build(ast.Assert, expr, msg, assert_node)

    def handle_typed_suite(self, suite_node):
        type_comment = None
        first_child = suite_node.get_child(0)
        if first_child.type == syms.simple_stmt:
            end = first_child.num_children() - 1
            if first_child.get_child(end - 1).type == tokens.SEMI:
                end -= 1
            stmts = [self.handle_stmt(first_child.get_child(i))
                     for i in range(0, end, 2)]
        else:
            stmts = []
            start = 1
            type_comment, has_type_comment = self.handle_type_comment(suite_node.get_child(start))
            if has_type_comment:
                start += 2

            for i in range(start+1, suite_node.num_children() - 1):
                stmt = suite_node.get_child(i)
                stmt_count = self.number_of_statements(stmt)
                if stmt_count == 1:
                    stmts.append(self.handle_stmt(stmt))
                else:
                    simple_stmt = stmt.get_child(0)
                    for j in range(0, simple_stmt.num_children(), 2):
                        stmt = simple_stmt.get_child(j)
                        if not stmt.num_children():
                            break
                        stmts.append(self.handle_stmt(stmt))
        return stmts, type_comment

    def handle_suite(self, suite_node):
        stmts, type_comment = self.handle_typed_suite(suite_node)
        assert self.space.is_none(type_comment)
        return stmts

    def handle_if_stmt(self, if_node):
        child_count = if_node.num_children()
        if child_count == 4:
            test = self.handle_expr(if_node.get_child(1))
            suite = self.handle_suite(if_node.get_child(3))
            return build(ast.If, test, suite, None, if_node)
        otherwise_string = if_node.get_child(4).get_value()
        if otherwise_string == "else":
            test = self.handle_expr(if_node.get_child(1))
            suite = self.handle_suite(if_node.get_child(3))
            else_suite = self.handle_suite(if_node.get_child(6))
            return build(ast.If, test, suite, else_suite, if_node)
        elif otherwise_string == "elif":
            elif_count = child_count - 4
            after_elif = if_node.get_child(elif_count + 1)
            if after_elif.type == tokens.NAME and \
                    after_elif.get_value() == "else":
                has_else = True
                elif_count -= 3
            else:
                has_else = False
            elif_count /= 4
            if has_else:
                last_elif_node = if_node.get_child(-7)
                last_elif = if_node.get_child(-6)
                last_elif_test = self.handle_expr(last_elif)
                elif_body = self.handle_suite(if_node.get_child(-4))
                else_body = self.handle_suite(if_node.get_child(-1))
                otherwise = [build(ast.If, last_elif_test, elif_body, else_body, last_elif_node)]
                elif_count -= 1
            else:
                otherwise = None
            for i in range(elif_count):
                offset = 5 + (elif_count - i - 1) * 4
                elif_node = if_node.get_child(offset - 1)
                elif_test_node = if_node.get_child(offset)
                elif_test = self.handle_expr(elif_test_node)
                elif_body = self.handle_suite(if_node.get_child(offset + 2))
                new_if = build(ast.If, elif_test, elif_body, otherwise, elif_node)
                otherwise = [new_if]
            expr = self.handle_expr(if_node.get_child(1))
            body = self.handle_suite(if_node.get_child(3))
            return build(ast.If, expr, body, otherwise, if_node)
        else:
            raise AssertionError("unknown if statement configuration")

    def handle_while_stmt(self, while_node):
        loop_test = self.handle_expr(while_node.get_child(1))
        body = self.handle_suite(while_node.get_child(3))
        if while_node.num_children() == 7:
            otherwise = self.handle_suite(while_node.get_child(6))
        else:
            otherwise = None
        return build(ast.While, loop_test, body, otherwise, while_node)

    def handle_type_comment(self, comment):
        if comment.type == tokens.TYPE_COMMENT:
            value = self.space.newtext(comment.get_value())
            return value, True
        else:
            return self.space.w_None, False

    def handle_for_stmt(self, for_node, is_async, posnode=None):
        self.check_feature(
            is_async,
            version=5,
            msg="Async for loops are only supported in Python 3.5 and greater",
            n=for_node
        )
        if posnode is None:
            posnode = for_node
        target_node = for_node.get_child(1)
        target_as_exprlist = self.handle_exprlist(target_node, ast.Store)
        if target_node.num_children() == 1:
            target = target_as_exprlist[0]
        else:
            target = build(ast.Tuple, target_as_exprlist, ast.Store, target_node)
        expr = self.handle_testlist(for_node.get_child(3))
        type_comment, has_type_comment = self.handle_type_comment(for_node.get_child(5))
        body = self.handle_suite(for_node.get_child(has_type_comment + 5))
        if for_node.num_children() == has_type_comment + 9:
            otherwise = self.handle_suite(for_node.get_child(has_type_comment + 8))
        else:
            otherwise = None
        if is_async:
            return build(ast.AsyncFor, target, expr, body, otherwise, type_comment, posnode)
        else:
            return build(ast.For, target, expr, body, otherwise, type_comment, posnode)

    def handle_except_clause(self, exc, body):
        test = None
        name = None
        suite = self.handle_suite(body)
        child_count = exc.num_children()
        if child_count >= 2:
            test = self.handle_expr(exc.get_child(1))
        if child_count == 4:
            name_node = exc.get_child(3)
            name = self.new_identifier(name_node.get_value())
            self.check_forbidden_name(name, name_node)
        return build(ast.ExceptHandler, test, name, suite, exc)

    def handle_try_stmt(self, try_node):
        body = self.handle_suite(try_node.get_child(2))
        child_count = try_node.num_children()
        except_count = (child_count - 3 ) // 3
        otherwise = None
        finally_suite = None
        possible_extra_clause = try_node.get_child(-3)
        if possible_extra_clause.type == tokens.NAME:
            if possible_extra_clause.get_value() == "finally":
                if child_count >= 9 and \
                        try_node.get_child(-6).type == tokens.NAME:
                    otherwise = self.handle_suite(try_node.get_child(-4))
                    except_count -= 1
                finally_suite = self.handle_suite(try_node.get_child(-1))
                except_count -= 1
            else:
                otherwise = self.handle_suite(try_node.get_child(-1))
                except_count -= 1
        handlers = []
        if except_count:
            for i in range(except_count):
                base_offset = i * 3
                exc = try_node.get_child(3 + base_offset)
                except_body = try_node.get_child(5 + base_offset)
                handlers.append(self.handle_except_clause(exc, except_body))
        return build(ast.Try, body, handlers, otherwise, finally_suite, try_node)

    def handle_with_item(self, item_node):
        test = self.handle_expr(item_node.get_child(0))
        if item_node.num_children() == 3:
            target = self.handle_expr(item_node.get_child(2))
            self.set_context(target, ast.Store)
        else:
            target = None
        return ast.withitem(test, target)

    def handle_with_stmt(self, with_node, is_async, posnode=None):
        self.check_feature(
            is_async,
            version=5,
            msg="Async with statements are only supported in Python 3.5 and greater",
            n=with_node
        )
        if posnode is None:
            posnode = with_node
        body = self.handle_suite(with_node.get_child(-1))
        type_comment, has_type_comment = self.handle_type_comment(with_node.get_child(-2))
        num_children = with_node.num_children() - has_type_comment
        items = [self.handle_with_item(with_node.get_child(i))
                 for i in range(1, num_children-2, 2)]
        if is_async:
            return build(ast.AsyncWith, items, body, type_comment, posnode)
        else:
            return build(ast.With, items, body, type_comment, posnode)

    def handle_classdef(self, classdef_node, decorators=None):
        name_node = classdef_node.get_child(1)
        name = self.new_identifier(name_node.get_value())
        self.check_forbidden_name(name, name_node)
        if classdef_node.num_children() == 4:
            # class NAME ':' suite
            body = self.handle_suite(classdef_node.get_child(3))
            return build(ast.ClassDef, name, None, None, body, decorators, classdef_node)
        if classdef_node.get_child(3).type == tokens.RPAR:
            # class NAME '(' ')' ':' suite
            body = self.handle_suite(classdef_node.get_child(5))
            return build(ast.ClassDef, name, None, None, body, decorators,
                                classdef_node)

        # class NAME '(' arglist ')' ':' suite
        # build up a fake Call node so we can extract its pieces
        call_name = build(ast.Name, name, ast.Load, classdef_node)
        call = self.handle_call(classdef_node.get_child(3), call_name, genexp_allowed=False)
        body = self.handle_suite(classdef_node.get_child(6))
        return build(ast.ClassDef,
            name, call.args, call.keywords,
            body, decorators, classdef_node)

    def handle_funcdef_impl(self, funcdef_node, is_async, decorators=None, posnode=None):
        self.check_feature(
            is_async,
            version=5,
            msg="Async functions are only supported in Python 3.5 and greater",
            n=funcdef_node
        )
        if posnode is None:
            posnode = funcdef_node
        name_node = funcdef_node.get_child(1)
        name = self.new_identifier(name_node.get_value())
        self.check_forbidden_name(name, name_node)
        args = self.handle_arguments(funcdef_node.get_child(2))
        suite = 4
        returns = None
        if funcdef_node.get_child(3).type == tokens.RARROW:
            returns = self.handle_expr(funcdef_node.get_child(4))
            suite += 2
        type_comment, has_type_comment = self.handle_type_comment(funcdef_node.get_child(suite))
        suite += has_type_comment
        body, possible_type_comment = self.handle_typed_suite(funcdef_node.get_child(suite))
        if not self.space.is_none(possible_type_comment):
            if not self.space.is_none(type_comment):
                raise SyntaxError(
                    "Cannot have two type comments on def",
                    funcdef_node.get_lineno(),
                    funcdef_node.get_column()
                )
            type_comment = possible_type_comment
        assert len(body)
        if is_async:
            return ast.AsyncFunctionDef(name, args, body, decorators, returns, type_comment,
                                   posnode.get_lineno(), posnode.get_column(),
                                   body[-1].end_lineno, body[-1].end_col_offset)
        else:
            return ast.FunctionDef(name, args, body, decorators, returns, type_comment,
                                   posnode.get_lineno(), posnode.get_column(),
                                   body[-1].end_lineno, body[-1].end_col_offset)

    def handle_async_funcdef(self, node, decorators=None):
        return self.handle_funcdef_impl(node.get_child(1), 1, decorators, posnode=node)

    def handle_funcdef(self, node, decorators=None):
        return self.handle_funcdef_impl(node, 0, decorators)

    def handle_async_stmt(self, node):
        ch = node.get_child(1)
        if ch.type == syms.funcdef:
            return self.handle_funcdef_impl(ch, 1, posnode=node)
        elif ch.type == syms.with_stmt:
            return self.handle_with_stmt(ch, 1, posnode=node)
        elif ch.type == syms.for_stmt:
            return self.handle_for_stmt(ch, 1, posnode=node)
        else:
            raise AssertionError("invalid async statement")

    def handle_decorated(self, decorated_node):
        decorators = self.handle_decorators(decorated_node.get_child(0))
        definition = decorated_node.get_child(1)
        if definition.type == syms.funcdef:
            node = self.handle_funcdef(definition, decorators)
        elif definition.type == syms.classdef:
            node = self.handle_classdef(definition, decorators)
        elif definition.type == syms.async_funcdef:
            node = self.handle_async_funcdef(definition, decorators)
        else:
            raise AssertionError("unkown decorated")
        return node

    def handle_decorators(self, decorators_node):
        return [self.handle_decorator(decorators_node.get_child(i))
                    for i in range(decorators_node.num_children())]

    def handle_decorator(self, decorator_node):
        dec_name = self.handle_dotted_name(decorator_node.get_child(1))
        if decorator_node.num_children() == 3:
            dec = dec_name
        elif decorator_node.num_children() == 5:
            dec = ast.Call(
                dec_name, None, None, dec_name.lineno, dec_name.col_offset,
                decorator_node.get_end_lineno(),
                decorator_node.get_end_column())
        else:
            dec = self.handle_call(
                decorator_node.get_child(3), dec_name,
                lpar_node=decorator_node.get_child(2),
                rpar_node=decorator_node.get_child(4))
        return dec

    def handle_dotted_name(self, dotted_name_node):
        base_value = self.new_identifier(dotted_name_node.get_child(0).get_value())
        name = build(ast.Name, base_value, ast.Load, dotted_name_node)
        for i in range(2, dotted_name_node.num_children(), 2):
            attr_node = dotted_name_node.get_child(i)
            attr = attr_node.get_value()
            attr = self.new_identifier(attr)
            name = build(ast.Attribute, name, attr, ast.Load, dotted_name_node)
            name.copy_location(dotted_name_node, attr_node)
        return name

    def handle_arguments(self, arguments_node):
        # This function handles both typedargslist (function definition)
        # and varargslist (lambda definition).
        if arguments_node.type == syms.parameters:
            if arguments_node.num_children() == 2:
                return ast.arguments(None, None, None, None, None, None, None)
            arguments_node = arguments_node.get_child(1)
        i = 0
        child_count = arguments_node.num_children()
        n_posonly = 0
        n_pos = 0
        n_pos_def = 0
        n_kwdonly = 0
        # scan args

        while i < child_count:
            arg_type = arguments_node.get_child(i).type
            if arg_type == tokens.STAR:
                i += 1
                if i < child_count:
                    next_arg_type = arguments_node.get_child(i).type
                    if (next_arg_type == syms.tfpdef or
                        next_arg_type == syms.vfpdef):
                        i += 1
                break
            if arg_type == tokens.DOUBLESTAR:
                break
            if arg_type == syms.vfpdef or arg_type == syms.tfpdef:
                n_pos += 1
            elif arg_type == tokens.EQUAL:
                n_pos_def += 1
            elif arg_type == tokens.SLASH:
                # all positional args seen so far are positional only
                n_posonly = n_pos
                n_pos = 0
            i += 1
        while i < child_count:
            arg_type = arguments_node.get_child(i).type
            if arg_type == tokens.DOUBLESTAR:
                break
            if arg_type == syms.vfpdef or arg_type == syms.tfpdef:
                n_kwdonly += 1
            i += 1
        posonly = None
        pos = []
        posdefaults = []
        kwonly = [] if n_kwdonly else None
        kwdefaults = []
        kwarg = None
        vararg = None
        last_arg = None
        # process args
        i = 0
        have_default = False
        while i < child_count:
            arg = arguments_node.get_child(i)
            arg_type = arg.type
            if arg_type == syms.tfpdef or arg_type == syms.vfpdef:
                if i + 1 < child_count and \
                        arguments_node.get_child(i + 1).type == tokens.EQUAL:
                    default_node = arguments_node.get_child(i + 2)
                    posdefaults.append(self.handle_expr(default_node))
                    i += 2
                    have_default = True
                elif have_default:
                    msg = "non-default argument follows default argument"
                    self.error(msg, arguments_node)
                last_arg = self.handle_arg(arg)
                pos.append(last_arg)
                i += 1
                if i < child_count:
                    i += arguments_node.get_child(i).type == tokens.COMMA
            elif arg_type == tokens.STAR:
                if i + 1 >= child_count:
                    self.error("named arguments must follow bare *",
                               arguments_node)
                name_node = arguments_node.get_child(i + 1)
                keywordonly_args = []
                if name_node.type == tokens.COMMA:
                    i += 2
                    i = self.handle_keywordonly_args(arguments_node, i, kwonly,
                                                     kwdefaults)
                else:
                    vararg = last_arg = self.handle_arg(name_node)
                    i += 2
                    if i < child_count:
                        i += arguments_node.get_child(i).type == tokens.COMMA
                    if i < child_count:
                        next_arg_type = arguments_node.get_child(i).type
                        if (next_arg_type == syms.tfpdef or
                            next_arg_type == syms.vfpdef):
                            i = self.handle_keywordonly_args(arguments_node, i,
                                                             kwonly, kwdefaults)
            elif arg_type == tokens.DOUBLESTAR:
                name_node = arguments_node.get_child(i + 1)
                kwarg = last_arg = self.handle_arg(name_node)
                i += 2
                if i < child_count:
                    i += arguments_node.get_child(i).type == tokens.COMMA
            elif arg_type == tokens.TYPE_COMMENT:
                assert last_arg is not None
                last_arg.type_comment, _ = self.handle_type_comment(arg)
                i += 1
            elif arg_type == tokens.SLASH:
                posonly = pos
                pos = []
                i += 2
            else:
                raise AssertionError("unknown node in argument list")
        assert n_posonly == 0 or len(posonly) == n_posonly
        return ast.arguments(posonly, pos, vararg, kwonly, kwdefaults, kwarg,
                             posdefaults)

    def handle_keywordonly_args(self, arguments_node, i, kwonly, kwdefaults):
        if kwonly is None:
            self.error("named arguments must follows bare *",
                       arguments_node.get_child(i))
        child_count = arguments_node.num_children()
        last_arg = None
        while i < child_count:
            arg = arguments_node.get_child(i)
            arg_type = arg.type
            if arg_type == syms.vfpdef or arg_type == syms.tfpdef:
                if (i + 1 < child_count and
                    arguments_node.get_child(i + 1).type == tokens.EQUAL):
                    expr = self.handle_expr(arguments_node.get_child(i + 2))
                    kwdefaults.append(expr)
                    i += 2
                else:
                    kwdefaults.append(None)
                ann = None
                if arg.num_children() == 3:
                    ann = self.handle_expr(arg.get_child(2))
                name_node = arg.get_child(0)
                argname = name_node.get_value()
                argname = self.new_identifier(argname)
                self.check_forbidden_name(argname, name_node)
                type_comment = self.space.w_None
                last_arg = build(ast.arg, argname, ann, type_comment, arg)
                kwonly.append(last_arg)
                i += 1
                if i < child_count:
                    i += arguments_node.get_child(i).type == tokens.COMMA
            elif arg_type == tokens.DOUBLESTAR:
                return i
            elif arg_type == tokens.TYPE_COMMENT:
                assert last_arg is not None
                last_arg.type_comment, _ = self.handle_type_comment(arg)
                i += 1
        return i

    def handle_arg(self, arg_node):
        name_node = arg_node.get_child(0)
        name = self.new_identifier(name_node.get_value())
        self.check_forbidden_name(name, arg_node)
        ann = None
        if arg_node.num_children() == 3:
            ann = self.handle_expr(arg_node.get_child(2))
        type_comment = self.space.w_None
        return build(ast.arg, name, ann, type_comment, arg_node)

    def handle_stmt(self, stmt):
        stmt_type = stmt.type
        if stmt_type == syms.stmt:
            stmt = stmt.get_child(0)
            stmt_type = stmt.type
        if stmt_type == syms.simple_stmt:
            stmt = stmt.get_child(0)
            stmt_type = stmt.type
        if stmt_type == syms.small_stmt:
            stmt = stmt.get_child(0)
            stmt_type = stmt.type
            if stmt_type == syms.expr_stmt:
                return self.handle_expr_stmt(stmt)
            elif stmt_type == syms.del_stmt:
                return self.handle_del_stmt(stmt)
            elif stmt_type == syms.pass_stmt:
                return build(ast.Pass, stmt)
            elif stmt_type == syms.flow_stmt:
                return self.handle_flow_stmt(stmt)
            elif stmt_type == syms.import_stmt:
                return self.handle_import_stmt(stmt)
            elif stmt_type == syms.global_stmt:
                return self.handle_global_stmt(stmt)
            elif stmt_type == syms.nonlocal_stmt:
                return self.handle_nonlocal_stmt(stmt)
            elif stmt_type == syms.assert_stmt:
                return self.handle_assert_stmt(stmt)
            else:
                raise AssertionError("unhandled small statement")
        elif stmt_type == syms.compound_stmt:
            stmt = stmt.get_child(0)
            stmt_type = stmt.type
            if stmt_type == syms.if_stmt:
                return self.handle_if_stmt(stmt)
            elif stmt_type == syms.while_stmt:
                return self.handle_while_stmt(stmt)
            elif stmt_type == syms.for_stmt:
                return self.handle_for_stmt(stmt, 0)
            elif stmt_type == syms.try_stmt:
                return self.handle_try_stmt(stmt)
            elif stmt_type == syms.with_stmt:
                return self.handle_with_stmt(stmt, 0)
            elif stmt_type == syms.funcdef:
                return self.handle_funcdef(stmt)
            elif stmt_type == syms.classdef:
                return self.handle_classdef(stmt)
            elif stmt_type == syms.decorated:
                return self.handle_decorated(stmt)
            elif stmt_type == syms.async_stmt:
                return self.handle_async_stmt(stmt)
            else:
                raise AssertionError("unhandled compound statement")
        else:
            raise AssertionError("unknown statment type")

    def handle_expr_stmt(self, stmt):
        from pypy.interpreter.pyparser.parser import AbstractNonterminal
        if stmt.num_children() == 1:
            expression = self.handle_testlist(stmt.get_child(0))
            return build(ast.Expr, expression, stmt)
        elif stmt.get_child(1).type == syms.augassign:
            # Augmented assignment.
            target_child = stmt.get_child(0)
            target_expr = self.handle_testlist(target_child)
            self.set_context(target_expr, ast.Store)
            value_child = stmt.get_child(2)
            if value_child.type == syms.testlist:
                value_expr = self.handle_testlist(value_child)
            else:
                value_expr = self.handle_expr(value_child)
            op_str = stmt.get_child(1).get_child(0).get_value()
            operator = augassign_operator_map[op_str]
            self.check_feature(
                operator is ast.MatMult,
                version=5,
                msg="The '@' operator is only supported in Python 3.5 and greater",
                n=stmt
            )
            return build(ast.AugAssign, target_expr, operator, value_expr,
                                 stmt)
        elif stmt.get_child(1).type == syms.annassign:
            # Variable annotation (PEP 526), which may or may not include assignment.
            self.check_feature(
                condition=True,
                version=6,
                msg="Variable annotation syntax is only supported in Python 3.6 and greater",
                n=stmt
            )
            target = stmt.get_child(0)
            target_expr = self.handle_testlist(target)
            simple = 0
            # target is a name, nothing funky
            if isinstance(target_expr, ast.Name):
                # The PEP demands that `(x): T` be treated differently than `x: T`
                # however, the parser does not easily expose the wrapping parens, which are a no-op
                # they are elided by handle_testlist if they existed.
                # so here we walk down the parse tree until we hit a terminal, and check whether it's
                # a left paren
                simple_test = target.get_child(0)
                while isinstance(simple_test, AbstractNonterminal):
                    simple_test = simple_test.get_child(0)
                if simple_test.type != tokens.LPAR:
                    simple = 1
            # subscripts are allowed with nothing special
            elif isinstance(target_expr, ast.Subscript):
                pass
            # attributes are also fine here
            elif isinstance(target_expr, ast.Attribute):
                pass
            # tuples and lists get special error messages
            elif isinstance(target_expr, ast.Tuple):
                self.error("only single target (not tuple) can be annotated", target)
            elif isinstance(target_expr, ast.List):
                self.error("only single target (not list) can be annotated", target)
            # and everything else gets a generic error
            else:
                self.error("illegal target for annotation", target)
            self.set_context(target_expr, ast.Store)
            second = stmt.get_child(1)
            annotation = self.handle_expr(second.get_child(1))
            value_expr = None
            if second.num_children() == 4:
                value_child = second.get_child(-1)
                if value_child.type == syms.testlist_star_expr:
                    value_expr = self.handle_testlist(value_child)
                else:
                    value_expr = self.handle_expr(value_child)
            return build(ast.AnnAssign, target_expr, annotation, value_expr, simple, stmt)
        else:
            # Normal assignment.
            targets = []
            num_children = stmt.num_children()
            type_comment, has_type_comment = self.handle_type_comment(stmt.get_child(-1))
            num_children -= has_type_comment

            for i in range(0, num_children - 2, 2):
                target_node = stmt.get_child(i)
                if target_node.type == syms.yield_expr:
                    self.error("assignment to yield expression not possible",
                               target_node)
                target_expr = self.handle_testlist(target_node)
                self.set_context(target_expr, ast.Store)
                targets.append(target_expr)
            value_child = stmt.get_child(num_children-1)
            if value_child.type == syms.testlist_star_expr:
                value_expr = self.handle_testlist(value_child)
            else:
                value_expr = self.handle_expr(value_child)
            return build(ast.Assign, targets, value_expr, type_comment, stmt)

    def get_expression_list(self, tests):
        return [self.handle_expr(tests.get_child(i))
                for i in range(0, tests.num_children(), 2)]

    def handle_testlist(self, tests, atom_node=None):
        if tests.num_children() == 1:
            return self.handle_expr(tests.get_child(0))
        else:
            elts = self.get_expression_list(tests)
            result = build(ast.Tuple, elts, ast.Load, tests)
            if atom_node:
                result.copy_location(atom_node)
            return result

    def handle_expr(self, expr_node):
        # Loop until we return something.
        while True:
            expr_node_type = expr_node.type
            if expr_node_type == syms.test or expr_node_type == syms.test_nocond:
                first_child = expr_node.get_child(0)
                if first_child.type in (syms.lambdef, syms.lambdef_nocond):
                    return self.handle_lambdef(first_child)
                elif expr_node.num_children() > 1:
                    return self.handle_ifexp(expr_node)
                else:
                    expr_node = first_child
            elif expr_node_type == syms.namedexpr_test:
                if expr_node.num_children() == 1:
                    expr_node = expr_node.get_child(0)
                    continue
                return self.handle_namedexpr(expr_node)
            elif expr_node_type == syms.or_test or \
                    expr_node_type == syms.and_test:
                if expr_node.num_children() == 1:
                    expr_node = expr_node.get_child(0)
                    continue
                seq = [self.handle_expr(expr_node.get_child(i))
                       for i in range(0, expr_node.num_children(), 2)]
                if expr_node_type == syms.or_test:
                    op = ast.Or
                else:
                    op = ast.And
                return build(ast.BoolOp, op, seq, expr_node)
            elif expr_node_type == syms.not_test:
                if expr_node.num_children() == 1:
                    expr_node = expr_node.get_child(0)
                    continue
                expr = self.handle_expr(expr_node.get_child(1))
                return build(ast.UnaryOp, ast.Not, expr, expr_node)
            elif expr_node_type == syms.comparison:
                if expr_node.num_children() == 1:
                    expr_node = expr_node.get_child(0)
                    continue
                operators = []
                operands = []
                expr = self.handle_expr(expr_node.get_child(0))
                for i in range(1, expr_node.num_children(), 2):
                    operators.append(self.handle_comp_op(expr_node.get_child(i)))
                    operands.append(self.handle_expr(expr_node.get_child(i + 1)))
                return build(ast.Compare, expr, operators, operands, expr_node)
            elif expr_node_type == syms.star_expr:
                return self.handle_star_expr(expr_node)
            elif expr_node_type == syms.expr or \
                    expr_node_type == syms.xor_expr or \
                    expr_node_type == syms.and_expr or \
                    expr_node_type == syms.shift_expr or \
                    expr_node_type == syms.arith_expr or \
                    expr_node_type == syms.term:
                if expr_node.num_children() == 1:
                    expr_node = expr_node.get_child(0)
                    continue
                return self.handle_binop(expr_node)
            elif expr_node_type == syms.yield_expr:
                is_from = False
                if expr_node.num_children() > 1:
                    arg_node = expr_node.get_child(1)  # yield arg
                    if arg_node.num_children() == 2:
                        is_from = True
                        expr = self.handle_expr(arg_node.get_child(1))
                    else:
                        expr = self.handle_testlist(arg_node.get_child(0))
                else:
                    expr = None
                if is_from:
                    return build(ast.YieldFrom, expr, expr_node)
                return build(ast.Yield, expr, expr_node)
            elif expr_node_type == syms.factor:
                if expr_node.num_children() == 1:
                    expr_node = expr_node.get_child(0)
                    continue
                return self.handle_factor(expr_node)
            elif expr_node_type == syms.power:
                return self.handle_power(expr_node)
            else:
                raise AssertionError("unknown expr")

    def handle_namedexpr(self, expr_node):
        target_expr = self.handle_expr(expr_node.get_child(0))
        if not isinstance(target_expr, ast.Name):
            assert isinstance(target_expr, ast.expr)
            raise SyntaxError(
                "cannot use assignment expressions with %s" % target_expr._get_descr(self.space),
                target_expr.lineno, target_expr.col_offset)
        self.set_context(target_expr, ast.Store)
        expr = self.handle_expr(expr_node.get_child(2))
        return build(ast.NamedExpr, target_expr, expr, expr_node)

    def handle_star_expr(self, star_expr_node):
        expr = self.handle_expr(star_expr_node.get_child(1))
        return build(ast.Starred, expr, ast.Load, star_expr_node)

    def handle_lambdef(self, lambdef_node):
        expr = self.handle_expr(lambdef_node.get_child(-1))
        if lambdef_node.num_children() == 3:
            args = ast.arguments(None, None, None, None, None, None, None)
        else:
            args = self.handle_arguments(lambdef_node.get_child(1))
        return build(ast.Lambda, args, expr, lambdef_node)

    def handle_ifexp(self, if_expr_node):
        body = self.handle_expr(if_expr_node.get_child(0))
        expression = self.handle_expr(if_expr_node.get_child(2))
        otherwise = self.handle_expr(if_expr_node.get_child(4))
        return build(ast.IfExp, expression, body, otherwise, if_expr_node)

    def handle_comp_op(self, comp_op_node):
        comp_node = comp_op_node.get_child(0)
        comp_type = comp_node.type
        if comp_op_node.num_children() == 1:
            if comp_type == tokens.LESS:
                return ast.Lt
            elif comp_type == tokens.GREATER:
                return ast.Gt
            elif comp_type == tokens.EQEQUAL:
                return ast.Eq
            elif comp_type == tokens.LESSEQUAL:
                return ast.LtE
            elif comp_type == tokens.GREATEREQUAL:
                return ast.GtE
            elif comp_type == tokens.NOTEQUAL:
                flufl = self.compile_info.flags & consts.CO_FUTURE_BARRY_AS_BDFL
                if flufl and comp_node.get_value() == '!=':
                    self.error("with Barry as BDFL, use '<>' instead of '!='", comp_node)
                elif not flufl and comp_node.get_value() == '<>':
                    self.error('invalid syntax', comp_node)
                return ast.NotEq
            elif comp_type == tokens.NAME:
                if comp_node.get_value() == "is":
                    return ast.Is
                elif comp_node.get_value() == "in":
                    return ast.In
                else:
                    raise AssertionError("invalid comparison")
            else:
                raise AssertionError("invalid comparison")
        else:
            if comp_op_node.get_child(1).get_value() == "in":
                return ast.NotIn
            elif comp_node.get_value() == "is":
                return ast.IsNot
            else:
                raise AssertionError("invalid comparison")

    def handle_binop(self, binop_node):
        left = self.handle_expr(binop_node.get_child(0))
        right = self.handle_expr(binop_node.get_child(2))
        op = operator_map(binop_node.get_child(1).type)
        self.check_feature(
            op is ast.MatMult,
            version=5,
            msg="The '@' operator is only supported in Python 3.5 and greater",
            n=binop_node
        )
        result = build(ast.BinOp, left, op, right, binop_node)
        result.copy_location(binop_node.get_child(0), binop_node.get_child(2))
        number_of_ops = (binop_node.num_children() - 1) / 2
        for i in range(1, number_of_ops):
            op_node = binop_node.get_child(i * 2 + 1)
            op = operator_map(op_node.type)
            self.check_feature(
                op is ast.MatMult,
                version=5,
                msg="The '@' operator is only supported in Python 3.5 and greater",
                n=binop_node
            )
            right_node = binop_node.get_child(i * 2 + 2)
            sub_right = self.handle_expr(right_node)
            result = build(ast.BinOp, result, op, sub_right, op_node)
            result.copy_location(binop_node, right_node)
        return result

    def handle_factor(self, factor_node):
        from pypy.interpreter.pyparser.parser import Terminal
        expr = self.handle_expr(factor_node.get_child(1))
        op_type = factor_node.get_child(0).type
        if op_type == tokens.PLUS:
            op = ast.UAdd
        elif op_type == tokens.MINUS:
            op = ast.USub
        elif op_type == tokens.TILDE:
            op = ast.Invert
        else:
            raise AssertionError("invalid factor node")
        return build(ast.UnaryOp, op, expr, factor_node)

    def handle_atom_expr(self, atom_node):
        start = 0
        num_ch = atom_node.num_children()
        if atom_node.get_child(0).type == tokens.AWAIT:
            self.check_feature(
                condition=True,
                version=5,
                msg="Await expressions are only supported in Python 3.5 and greater",
                n=atom_node
            )
            start = 1
        start_node = atom_node.get_child(start)
        atom_expr = self.handle_atom(start_node)
        if num_ch == 1:
            return atom_expr
        if start and num_ch == 2:
            return build(ast.Await, atom_expr, atom_node)

        for i in range(start+1, num_ch):
            trailer = atom_node.get_child(i)
            if trailer.type != syms.trailer:
                break
            tmp_atom_expr = self.handle_trailer(trailer, atom_expr, start_node)
            tmp_atom_expr.lineno = atom_expr.lineno
            tmp_atom_expr.col_offset = atom_expr.col_offset
            atom_expr = tmp_atom_expr
        if start:
            return build(ast.Await, atom_expr, atom_node)
        else:
            return atom_expr

    def handle_power(self, power_node):
        atom_expr = self.handle_atom_expr(power_node.get_child(0))
        if power_node.num_children() == 1:
            return atom_expr
        if power_node.get_child(-1).type == syms.factor:
            right = self.handle_expr(power_node.get_child(-1))
            atom_expr = build(ast.BinOp, atom_expr, ast.Pow, right, power_node)
        return atom_expr

    def handle_slice(self, slice_node):
        first_child = slice_node.get_child(0)
        if slice_node.num_children() == 1 and first_child.type == syms.test:
            index = self.handle_expr(first_child)
            return ast.Index(index)
        lower = None
        upper = None
        step = None
        if first_child.type == syms.test:
            lower = self.handle_expr(first_child)
        if first_child.type == tokens.COLON:
            if slice_node.num_children() > 1:
                second_child = slice_node.get_child(1)
                if second_child.type == syms.test:
                    upper = self.handle_expr(second_child)
        elif slice_node.num_children() > 2:
            third_child = slice_node.get_child(2)
            if third_child.type == syms.test:
                upper = self.handle_expr(third_child)
        last_child = slice_node.get_child(-1)
        if last_child.type == syms.sliceop:
            if last_child.num_children() != 1:
                step_child = last_child.get_child(1)
                if step_child.type == syms.test:
                    step = self.handle_expr(step_child)
        return ast.Slice(lower, upper, step)

    def handle_trailer(self, trailer_node, left_expr, start_node):
        result = self._handle_trailer(trailer_node, left_expr)
        return result.copy_location(start_node, trailer_node)

    def _handle_trailer(self, trailer_node, left_expr):
        first_child = trailer_node.get_child(0)
        if first_child.type == tokens.LPAR:
            if trailer_node.num_children() == 2:
                return build(ast.Call, left_expr, None, None, trailer_node)
            else:
                return self.handle_call(
                    trailer_node.get_child(1), left_expr,
                    lpar_node=first_child,
                    rpar_node=trailer_node.get_child(2))
        elif first_child.type == tokens.DOT:
            attr = self.new_identifier(trailer_node.get_child(1).get_value())
            return build(ast.Attribute, left_expr, attr, ast.Load, trailer_node)
        else:
            middle = trailer_node.get_child(1)
            if middle.num_children() == 1:
                slice = self.handle_slice(middle.get_child(0))
                return build(ast.Subscript, left_expr, slice, ast.Load, middle)
            slices = []
            simple = True
            for i in range(0, middle.num_children(), 2):
                slc = self.handle_slice(middle.get_child(i))
                if not isinstance(slc, ast.Index):
                    simple = False
                slices.append(slc)
            if not simple:
                ext_slice = ast.ExtSlice(slices)
                return build(ast.Subscript, left_expr, ext_slice, ast.Load, middle)
            elts = []
            for idx in slices:
                assert isinstance(idx, ast.Index)
                elts.append(idx.value)
            tup = build(ast.Tuple, elts, ast.Load, middle)
            return build(ast.Subscript, left_expr, ast.Index(tup), ast.Load, middle)

    def handle_call(self, args_node, callable_expr, genexp_allowed=True,
                    lpar_node=None, rpar_node=None):
        arg_count = 0 # position args + iterable args unpackings
        keyword_count = 0 # keyword args + keyword args unpackings
        generator_count = 0
        last_is_comma = False
        for i in range(args_node.num_children()):
            argument = args_node.get_child(i)
            if argument.type == syms.argument:
                if argument.num_children() == 1:
                    arg_count += 1
                elif argument.get_child(1).type == syms.comp_for:
                    generator_count += 1
                elif argument.get_child(0).type == tokens.STAR:
                    arg_count += 1
                else:
                    # argument.get_child(0).type == tokens.DOUBLESTAR
                    # or keyword arg
                    keyword_count += 1
            last_is_comma = argument.type == tokens.COMMA

        if generator_count and not genexp_allowed:
            self.error("generator expression can't be used as bases of class definition",
                       args_node)
        if (generator_count > 1 or
                (generator_count and (keyword_count or arg_count)) or
                (generator_count == 1 and last_is_comma)):
            self.error("Generator expression must be parenthesized "
                       "if not sole argument", args_node)
        args = []
        keywords = []
        used_keywords = {}
        doublestars_count = 0 # just keyword argument unpackings
        child_count = args_node.num_children()
        i = 0
        while i < child_count:
            argument = args_node.get_child(i)
            if argument.type == syms.argument:
                expr_node = argument.get_child(0)
                if argument.num_children() == 1 or (
                        argument.num_children() == 3 and
                        argument.get_child(1).type == tokens.COLONEQUAL):
                    # a positional argument
                    if keywords:
                        if doublestars_count:
                            self.error("positional argument follows "
                                       "keyword argument unpacking",
                                       expr_node)
                        else:
                            self.error("positional argument follows "
                                       "keyword argument",
                                       expr_node)
                    if argument.num_children() == 1:
                        arg = self.handle_expr(expr_node)
                    else:
                        arg = self.handle_namedexpr(argument)
                    args.append(arg)
                elif expr_node.type == tokens.STAR:
                    # an iterable argument unpacking
                    if doublestars_count:
                        self.error("iterable argument unpacking follows "
                                   "keyword argument unpacking",
                                   expr_node)
                    expr = self.handle_expr(argument.get_child(1))
                    args.append(build(ast.Starred, expr, ast.Load, expr_node))
                elif expr_node.type == tokens.DOUBLESTAR:
                    # a keyword argument unpacking
                    i += 1
                    expr = self.handle_expr(argument.get_child(1))
                    keywords.append(ast.keyword(None, expr))
                    doublestars_count += 1
                elif argument.get_child(1).type == syms.comp_for:
                    # the lone generator expression
                    arg = self.handle_genexp(argument)
                    arg.copy_location(lpar_node, rpar_node)
                    args.append(arg)
                else:
                    # a keyword argument
                    tks = expr_node.flatten()
                    if len(tks) != 1 or tks[0].type != tokens.NAME:
                        self.error('expression cannot contain assignment, '
                                   'perhaps you meant "=="?', expr_node)

                    keyword_expr = self.handle_expr(expr_node)
                    if isinstance(keyword_expr, ast.Constant):
                        d = keyword_expr._get_descr(self.space)
                        self.error("cannot assign to %s" % (d, ), expr_node)
                    assert isinstance(keyword_expr, ast.Name)
                    keyword = keyword_expr.id
                    if keyword in used_keywords:
                        self.error("keyword argument repeated: '%s'" % keyword, expr_node)
                    used_keywords[keyword] = None
                    self.check_forbidden_name(keyword, expr_node)
                    keyword_value = self.handle_expr(argument.get_child(2))
                    keywords.append(ast.keyword(keyword, keyword_value))
            i += 1
        if not args:
            args = None
        if not keywords:
            keywords = None
        return ast.Call(callable_expr, args, keywords, callable_expr.lineno,
                        callable_expr.col_offset, args_node.get_end_lineno(),
                        args_node.get_end_column())

    def parse_number(self, raw):
        base = 10
        if raw.startswith("-"):
            negative = True
            raw = raw.lstrip("-")
        else:
            negative = False
        if raw.startswith("0"):
            if len(raw) > 2 and raw[1] in "Xx":
                base = 16
            elif len(raw) > 2 and raw[1] in "Bb":
                base = 2
            ## elif len(raw) > 2 and raw[1] in "Oo": # Fallback below is enough
            ##     base = 8
            elif len(raw) > 1:
                base = 8
            # strip leading characters
            i = 0
            limit = len(raw) - 1
            while i < limit:
                if base == 16 and raw[i] not in "0xX":
                    break
                if base == 8 and raw[i] not in "0oO":
                    break
                if base == 2 and raw[i] not in "0bB":
                    break
                i += 1
            raw = raw[i:]
            if not raw[0].isdigit():
                raw = "0" + raw
        if negative:
            raw = "-" + raw
        w_num_str = self.space.newtext(raw)
        w_base = self.space.newint(base)
        if raw[-1] in "jJ":
            tp = self.space.w_complex
            return self.space.call_function(tp, w_num_str)
        try:
            return self.space.call_function(self.space.w_int, w_num_str, w_base)
        except error.OperationError as e:
            if not e.match(self.space, self.space.w_ValueError):
                raise
            return self.space.call_function(self.space.w_float, w_num_str)

    @always_inline
    def handle_dictelement(self, node, i):
        if node.get_child(i).type == tokens.DOUBLESTAR:
            key = None
            value = self.handle_expr(node.get_child(i+1))
            i += 2
        else:
            key = self.handle_expr(node.get_child(i))
            value = self.handle_expr(node.get_child(i+2))
            i += 3
        return (i,key,value)

    def handle_atom(self, atom_node):
        first_child = atom_node.get_child(0)
        first_child_type = first_child.type
        if first_child_type == tokens.NAME:
            name = first_child.get_value()
            if name == "None":
                w_singleton = self.space.w_None
            elif name == "True":
                w_singleton = self.space.w_True
            elif name == "False":
                w_singleton = self.space.w_False
            else:
                name = self.new_identifier(name)
                return build(ast.Name, name, ast.Load, first_child)
            return build(ast.Constant, w_singleton, self.space.w_None, first_child)
        #
        elif first_child_type == tokens.STRING:
            return fstring.string_parse_literal(self, atom_node)
        #
        elif first_child_type == tokens.NUMBER:
            self.check_feature(
                "_" in first_child.get_value(),
                version=6,
                msg="Underscores in numeric literals are only supported in Python 3.6 and greater",
                n=atom_node
            )
            num_value = self.parse_number(first_child.get_value())
            return build(ast.Constant, num_value, self.space.w_None, atom_node)
        elif first_child_type == tokens.ELLIPSIS:
            return build(ast.Constant, self.space.w_Ellipsis, self.space.w_None, atom_node)
        elif first_child_type == tokens.LPAR:
            second_child = atom_node.get_child(1)
            if second_child.type == tokens.RPAR:
                return build(ast.Tuple, None, ast.Load, atom_node)
            elif second_child.type == syms.yield_expr:
                return self.handle_expr(second_child)
            result = self.handle_testlist_gexp(second_child, atom_node)
            return result
        elif first_child_type == tokens.LSQB:
            second_child = atom_node.get_child(1)
            if second_child.type == tokens.RSQB:
                return build(ast.List, None, ast.Load, atom_node)
            if second_child.num_children() == 1 or \
                    second_child.get_child(1).type == tokens.COMMA:
                elts = self.get_expression_list(second_child)
                return build(ast.List, elts, ast.Load, atom_node)
            return self.handle_listcomp(second_child).copy_location(atom_node)
        elif first_child_type == tokens.LBRACE:
            maker = atom_node.get_child(1)
            n_maker_children = maker.num_children()
            if maker.type == tokens.RBRACE:
                # an empty dict
                return build(ast.Dict, None, None, atom_node)
            else:
                is_dict = maker.get_child(0).type == tokens.DOUBLESTAR
                if (n_maker_children == 1 or
                    (n_maker_children > 1 and
                     maker.get_child(1).type == tokens.COMMA)):
                    # a set display
                    return self.handle_setdisplay(maker, atom_node)
                elif n_maker_children > 1 and maker.get_child(1).type == syms.comp_for:
                    # a set comprehension
                    return self.handle_setcomp(maker, atom_node)
                elif (n_maker_children > (3-is_dict) and
                      maker.get_child(3-is_dict).type == syms.comp_for):
                    # a dictionary comprehension
                    if is_dict:
                        raise self.error("dict unpacking cannot be used in "
                                         "dict comprehension", atom_node)
                    return self.handle_dictcomp(maker, atom_node)
                else:
                    # a dictionary display
                    return self.handle_dictdisplay(maker, atom_node)
        elif first_child_type == tokens.REVDBMETAVAR:
            string = atom_node.get_child(0).get_value()
            return build(ast.RevDBMetaVar, int(string[1:]), atom_node)
        else:
            raise AssertionError("unknown atom")

    def handle_testlist_gexp(self, gexp_node, atom_node=None):
        if gexp_node.num_children() > 1 and \
                gexp_node.get_child(1).type == syms.comp_for:
            result = self.handle_genexp(gexp_node)
            return result.copy_location(atom_node)
        return self.handle_testlist(gexp_node, atom_node)

    def count_comp_fors(self, comp_node):
        count = 0
        current_for = comp_node
        while True:
            count += 1
            is_async = current_for.get_child(0).type == tokens.ASYNC
            current_for = current_for.get_child(int(is_async))
            assert current_for.type == syms.sync_comp_for
            if current_for.num_children() == 5:
                current_iter = current_for.get_child(4)
            else:
                return count
            while True:
                first_child = current_iter.get_child(0)
                if first_child.type == syms.comp_for:
                    current_for = current_iter.get_child(0)
                    break
                elif first_child.type == syms.comp_if:
                    if first_child.num_children() == 3:
                        current_iter = first_child.get_child(2)
                    else:
                        return count
                else:
                    raise AssertionError("should not reach here")

    def count_comp_ifs(self, iter_node):
        count = 0
        while True:
            first_child = iter_node.get_child(0)
            if first_child.type == syms.comp_for:
                return count
            count += 1
            if first_child.num_children() == 2:
                return count
            iter_node = first_child.get_child(2)

    def comprehension_helper(self, comp_node):
        assert comp_node.type == syms.comp_for
        fors_count = self.count_comp_fors(comp_node)
        comps = []
        for i in range(fors_count):
            is_async = comp_node.get_child(0).type == tokens.ASYNC
            self.check_feature(
                is_async,
                version=6,
                msg="Async comprehensions are only supported in Python 3.6 and greater",
                n=comp_node
            )
            comp_node = comp_node.get_child(int(is_async))
            assert comp_node.type == syms.sync_comp_for
            for_node = comp_node.get_child(1)
            for_targets = self.handle_exprlist(for_node, ast.Store)
            expr = self.handle_expr(comp_node.get_child(3))
            assert isinstance(expr, ast.expr)
            if for_node.num_children() == 1:
                comp = ast.comprehension(for_targets[0], expr, None, is_async)
            else:
                # Modified in python2.7, see http://bugs.python.org/issue6704
                # Fixing unamed tuple location
                expr_node = for_targets[0]
                assert isinstance(expr_node, ast.expr)
                col = expr_node.col_offset
                line = expr_node.lineno
                target = ast.Tuple(for_targets, ast.Store, line, col,
                        expr_node.end_lineno, expr_node.end_col_offset)
                comp = ast.comprehension(target, expr, None, is_async)
            if comp_node.num_children() == 5:
                comp_node = comp_iter = comp_node.get_child(4)
                assert comp_iter.type == syms.comp_iter
                ifs_count = self.count_comp_ifs(comp_iter)
                if ifs_count:
                    ifs = []
                    for j in range(ifs_count):
                        comp_node = comp_if = comp_iter.get_child(0)
                        ifs.append(self.handle_expr(comp_if.get_child(1)))
                        if comp_if.num_children() == 3:
                            comp_node = comp_iter = comp_if.get_child(2)
                    comp.ifs = ifs
                if comp_node.type == syms.comp_iter:
                    comp_node = comp_node.get_child(0)
            assert isinstance(comp, ast.comprehension)
            comps.append(comp)
        return comps

    def handle_genexp(self, genexp_node):
        ch = genexp_node.get_child(0)
        elt = self.handle_expr(ch)
        if isinstance(elt, ast.Starred):
            self.error("iterable unpacking cannot be used in comprehension", ch)
        comps = self.comprehension_helper(genexp_node.get_child(1))
        return build(ast.GeneratorExp, elt, comps, genexp_node)

    def handle_listcomp(self, listcomp_node):
        ch = listcomp_node.get_child(0)
        elt = self.handle_expr(ch)
        if isinstance(elt, ast.Starred):
            self.error("iterable unpacking cannot be used in comprehension", ch)
        comps = self.comprehension_helper(listcomp_node.get_child(1))
        return build(ast.ListComp, elt, comps, listcomp_node)

    def handle_setcomp(self, set_maker, atom_node):
        ch = set_maker.get_child(0)
        elt = self.handle_expr(ch)
        if isinstance(elt, ast.Starred):
            self.error("iterable unpacking cannot be used in comprehension", ch)
        comps = self.comprehension_helper(set_maker.get_child(1))
        return build(ast.SetComp, elt, comps, atom_node)

    def handle_dictcomp(self, dict_maker, atom_node):
        i, key, value = self.handle_dictelement(dict_maker, 0)
        comps = self.comprehension_helper(dict_maker.get_child(i))
        return build(ast.DictComp, key, value, comps, atom_node)

    def handle_dictdisplay(self, node, atom_node):
        keys = []
        values = []
        i = 0
        while i < node.num_children():
            i, key, value = self.handle_dictelement(node, i)
            keys.append(key)
            values.append(value)
            i += 1
        return build(ast.Dict, keys, values, atom_node)

    def handle_setdisplay(self, node, atom_node):
        elts = []
        i = 0
        while i < node.num_children():
            expr = self.handle_expr(node.get_child(i))
            elts.append(expr)
            i += 2
        return build(ast.Set, elts, atom_node)

    def handle_exprlist(self, exprlist, context):
        exprs = []
        for i in range(0, exprlist.num_children(), 2):
            child = exprlist.get_child(i)
            expr = self.handle_expr(child)
            self.set_context(expr, context)
            exprs.append(expr)
        return exprs
