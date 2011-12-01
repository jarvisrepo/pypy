"""

                PyPy PPC Stackframe


            ---------------------------         --
            |                         |          |
            |      FPR SAVE AREA      |          |>> len(NONVOLATILES_FPR) * WORD
            |                         |          |
            ---------------------------         --
            |                         |          |
            |      GPR SAVE AREA      |          |>> len(NONVOLATILES) * WORD
            |                         |          |
            ---------------------------         --
            |                         |          |
            |   FLOAT/INT CONVERSION  |          |>> ? * WORD
            |                         |          |
            ---------------------------         --
            |                         |          |
            |       SPILLING AREA     |          |>> regalloc.frame_manager.frame_depth * WORD
            |  (LOCAL VARIABLE SPACE) |          |
            ---------------------------         --
            |                         |          |
            |      ENCODING AREA      |          |>> len(MANAGED_REGS) * WORD
            |      (ALLOCA AREA)      |          |
            ---------------------------         --
            |                         |          |
            |   PARAMETER SAVE AREA   |          |>> use MAX(number of parameters 
            |                         |          |   passed on stack in emit_call) * WORD
            ---------------------------         --  
            |        TOC POINTER      | WORD     |
            ---------------------------          |
            |       < RESERVED >      | WORD     |
            ---------------------------          |
            |       < RESERVED >      | WORD     |
            ---------------------------          |>> 6 WORDS
            |         SAVED LR        | WORD     |
            ---------------------------          |
            |         SAVED CR        | WORD     |
            ---------------------------          |
            |        BACK CHAIN       | WORD     |
     SP ->  ---------------------------         --


"""
