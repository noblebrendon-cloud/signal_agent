# Leviathon Architecture Simulator

## Architectural Overview
This page provides an explicit visualization layer tracing finite-state machine transitions executed in the backend architecture simulation loop.

## Changes Implemented for Stable Rendering
- Removed continuous physics-simulation models from `vis-network`.
- Placed all `canonicalNodes` on rigid exact X:Y coordinates so the layout resembles a professional topological representation natively. Nodes are explicitly flagged `fixed: true`.
- Integrated `diagnostics.js` capturing structured output to the browser console.
- Established a trace normalization layer adjusting variations like `Release Completed -> Release Complete` seamlessly.
- Built timeline playback logic utilizing `setInterval` to colorize nodes/edges temporally.

## Local Viewing
To load and preview the viewer properly resolving the `fetch` JSON constraints from external browser protections during development, run Python's built-in webserver.

```powershell
cd E:\signal_agent\laviathon\labs\simulator
python -m http.server 8000
```
Open a browser and navigate to `http://localhost:8000/`. The site should display the dark-themed view alongside the base populated topology map smoothly initialized within its rigid dimensions.

## Production Status
Because there are zero Node dependencies and all operations map internally generated JSON static files onto native Document Object bindings via purely client-side script execution, this repository is **100% Static-Host Safe**. It can be mounted directly onto GitHub Pages, AWS S3, or standard site infrastructure indefinitely.
