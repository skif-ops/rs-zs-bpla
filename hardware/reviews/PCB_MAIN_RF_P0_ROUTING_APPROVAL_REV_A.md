# PCB-MAIN RF P0 routing-subgate approval Rev.A

Decision: `ACCEPT_RF_P0_ROUTING_SUBGATE`  
Reviewer: `Скиф`  
Date: `2026-09-20`

The approval is bound to reviewed GitHub commit
`ae92a08a1a530e9d10eb6294481842ed68008469`, tree
`7eee7230005bddae5b3e389110d2204cac43ad8e`, and candidate-board SHA-256
`9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040`.

The reviewed machine gates are PCB Native Gate `#262`, run `35503671184`, and
CI `#534`, run `35503671273`; both concluded `success`.  KiCad 9 comparative
DRC retained `226 -> 226` total violations and `0 -> 0` errors while reducing
unconnected items from `444` to `429`.

Authorized scope:

- apply exactly the reviewed 138 F.Cu segments for the seven controlled RF nets;
- add no signal vias and preserve all 838 previously accepted copper objects;
- retain the reviewed `0.1509 mm` controlled RF width and candidate geometry;
- record the application separately against this immutable approval.

The authoritative board may equal the exact reviewed candidate after
application.  Any RF-geometry change requires a new controlled delta and
repeat machine and human review.

This approval does not declare routing, SI/PI, RF return-path review, final
fabricator stackup or impedance tolerance, Review B, CAM, DFM, procurement, or
manufacturing release complete.
