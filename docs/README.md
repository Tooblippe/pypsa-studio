
## Features
* Import and export networks in Pypsa Formats
* Drag and drop network builder
* Set up snapshots and multi-investment periods (needs attention)
* Auto routing network
* Region marker
* Zoom to a marked region
* Hide components
* Lock components and areas in place
* Open and run the current network in Jupyer Notebook
* Extensive PyPSA website examples
* Data view and editor
* All component parameters exposed
* Time series params exposed (needs attention)
* Re-route individual branches


## Why PyPSA-Studio

Currently there are no end to end [PyPSA gui](https://docs.pypsa.org/v1.0.5/user-guide/faq/#does-pypsa-have-a-gui).
The learning curve in especialy creating new networks in PyPSA can be difficult. 

This project aims to get new users up and running quickly to create a new network and start using it in Jupyer notebook 
if they want to, or export it for further use elsewhere. 


## Alternatives
I found this alternatives and attempts for review:
- [PyPSA Drawer](https://nimabahrami.github.io/pypsa-drawer/?trk=public_post_comment-text)
- [PyPSA network explorer](https://pypsa-explorer.streamlit.app/)



## Active development
This package is under active development.


## Platforms
The application has been tested on:
- Windows - Working
- Mac - Working
- Linux - to be tested


## Quick start
```
git clone https://github.com/Tooblippe/pypsa-studio.git
cd pypsa-studio
uv sync
uv run reflex run
```

# Installation
## Install uv
Install the uv package manager if you do not have it unstalled already.
[Instructions here](https://docs.astral.sh/uv/getting-started/installation/)

## Clone repo
```aiignore
git clone https://github.com/Tooblippe/pypsa-studio.git
cd pypsa-studio
```
## Run application
```
uv sync
uv run reflex run
```


# Application Navigation

![](imgs/navigation.png)

- Components pallet
  - Snapshots
  - Bus
  - Branch
  - Other
  - Types
- Controls
  - Auto route
  - Hide all
  - Show all
  - Mark region
  - Lock
  - Unlock
  - Undo 
  - Redo
- Canvas
- Components data
  - Component attributes

# Solving or interacting with network in Python
- Currently it will be best to run the network in [Jupyter](https://docs.jupyter.org/en/latest/)
- Create or load an `Examples` network 
- To run in `Jupyter` -  click `File` -> `Open in Jupyter`
- This will save your current network, open the Network in `Jupyer`, and run the first cell
- The network will be exposed as variable `n`
- Changes made to the network will not persist back to the original loaded network exept if you export the network and open it again in PyPSA-Studio (will improve on this!)
- If you do not want to use `Jupyter` just export the network and import it into an environment of your choice

  
# Sponsor – Africa Power Ventures

![](imgs/apv.png) 

APV design and implement dynamic electricity markets that also support wheeling, imports, exports and trading
- [About](https://afripow.com/services/)
- [Services](https://afripow.com/about-us/)
- [Twitter](https://x.com/Afripow/)
- [Linkedin](https://www.linkedin.com/company/africa-power-ventures/)


