


Phase 1
-------

 Canvas
  ======
  - add a right click handler that will open a 'context menu' when right clicking on a canvas object
  - just ad placeholder text for now.
  - each component type will have its own set of options.
  - design it so that it is extendable


Improve auto router
=======================
    -  show the current canvas zoom level
    -  when auto routing do not change the zoom level
    - after auto routing do a "fit view" this is native to react-flow
      - try not to cross lines.
      - what router type is being used?
      - let me know what optons are available durin the planning phase so we can decide how to deal with it



validate network
================
- add a button to validate if the network is actualy loadable in pypsa
- export the network, the other comonents, snapshots and multi_inestment peridos
- export the time series data and validate if the network will load
- add some form of trouble shooting to help user with what is wrong


ONe large view for all componetns files.
===========================================
- add a tabbed view for all the componontns, other, types, snapthost and timeseries data (if it exists and have values in it)
= make it editable so that for instance a user can quickly update some fields in all the "buses"
- make it persists
- not all vields e.g. busses will have all the fields present so endsure to build it from the data available and show all columns that has data and data
- the time series df can be very large so for now just sow the head. we will figure out what to do with it later
- if a component have a time seris make it possible to clikc on it and then open the tab with that attr and highlight that column


COmponetns and edges
====================
- design component svgs so that the edges make contact with the svg
- make it possible to click and move component labales. also save this x,y positions when saving exporing


Custom Router
==============