const DOM = {
    buttons: document.getElementById('scenario-buttons'),
    container: document.getElementById('graph-container'),
    fallback: document.getElementById('graph-fallback'),
    scenarioName: document.getElementById('val-scenario'),
    terminalState: document.getElementById('val-state'),
    transitions: document.getElementById('val-transitions'),
    playbackStatus: document.getElementById('val-playback'),
    tick: document.getElementById('val-tick'),
    currentAction: document.getElementById('val-current-action'),
    log: document.getElementById('scenario-log'),
    
    btnPlay: document.getElementById('btn-play'),
    btnPause: document.getElementById('btn-pause'),
    btnStep: document.getElementById('btn-step'),
    btnReset: document.getElementById('btn-reset'),
    selSpeed: document.getElementById('sel-speed')
};

// Diagnostics
const diag = window.Diag || { log: console.log, warn: console.warn, error: console.error };

// Normalization Map for variations in trace state names
const STATE_NORM_MAP = {
    "Protocol Validation": "Protocol Session",
    "Release Completed": "Release Complete"
};

function norm(stateName) {
    return STATE_NORM_MAP[stateName] || stateName;
}

// 1. DETERMINISTIC FIXED LAYOUT
const canonicalNodes = [
    { id: 'Init', label: 'Init', x: -650, y: 0, fixed: true },
    { id: 'Capture', label: 'Capture', x: -430, y: 0, fixed: true },
    { id: 'Protocol Session', label: 'Protocol Session', x: -180, y: 0, fixed: true },
    { id: 'Artifact Compile', label: 'Artifact Compile', x: 90, y: 0, fixed: true },
    { id: 'Publication Gate', label: 'Publication Gate', x: 360, y: 0, fixed: true },
    { id: 'Release Complete', label: 'Release Complete', x: 640, y: -140, fixed: true },
    { id: 'Blocked', label: 'Blocked', x: 640, y: 0, fixed: true },
    { id: 'Violation Halt', label: 'Violation Halt', x: 640, y: 140, fixed: true }
];

const canonicalEdges = [
    { id: 'Init-Capture', from: 'Init', to: 'Capture' },
    { id: 'Capture-Protocol Session', from: 'Capture', to: 'Protocol Session' },
    { id: 'Protocol Session-Artifact Compile', from: 'Protocol Session', to: 'Artifact Compile' },
    { id: 'Artifact Compile-Publication Gate', from: 'Artifact Compile', to: 'Publication Gate' },
    { id: 'Publication Gate-Release Complete', from: 'Publication Gate', to: 'Release Complete' },
    { id: 'Capture-Violation Halt', from: 'Capture', to: 'Violation Halt' },
    { id: 'Artifact Compile-Blocked', from: 'Artifact Compile', to: 'Blocked' }
];

let network = null;
let nodesData = new vis.DataSet(canonicalNodes);
let edgesData = new vis.DataSet(canonicalEdges);

let currentTrace = null;
let playbackInterval = null;
let currentTickIndex = 0;
let dynamicallyAddedEdges = [];

function initGraph() {
    diag.log("Initializing Graph canvas");
    if (DOM.fallback) DOM.fallback.style.display = 'none';

    const data = { nodes: nodesData, edges: edgesData };
    const options = {
        physics: false, // Critical for fixed layout
        nodes: {
            shape: 'box',
            font: { color: '#ffffff', face: 'Inter', size: 14 },
            color: { background: '#252530', border: '#3a3a45', highlight: { background: '#4a90e2', border: '#4a90e2' } },
            margin: 12,
            borderWidth: 2,
            shadow: { enabled: true, color: 'rgba(0,0,0,0.5)', size: 5, x: 2, y: 2 }
        },
        edges: {
            color: { color: '#555566', highlight: '#4a90e2' },
            arrows: 'to',
            smooth: { type: 'cubicBezier', forceDirection: 'none' },
            width: 2
        },
        interaction: { dragNodes: false, zoomView: true, dragView: true }
    };
    try {
        network = new vis.Network(DOM.container, data, options);
        network.once('afterDrawing', () => {
            network.fit();
        });
        diag.log("Graph initialized successfully");
    } catch (e) {
        diag.error("VisJS Network init failed", e);
        showFallback("Unable to render simulation graph. Graph initialization failed.");
    }
}

function showFallback(msg) {
    if (!DOM.fallback) {
        const d = document.createElement('div');
        d.id = 'graph-fallback';
        d.style.cssText = "display: flex; height: 100%; align-items: center; justify-content: center; color: #ef4444; font-size: 0.9rem; text-align: center; padding: 2rem;";
        DOM.container.appendChild(d);
        DOM.fallback = d;
    }
    DOM.fallback.style.display = 'flex';
    DOM.fallback.innerHTML = msg;
}

function resetGraphVisuals() {
    nodesData.forEach(n => {
        nodesData.update({ id: n.id, color: { background: '#252530', border: '#3a3a45' }});
    });
    edgesData.forEach(e => {
        edgesData.update({ id: e.id, color: { color: '#555566' }, width: 2, dashes: false });
    });
}

function getNodeColor(stateId, isTerminal) {
    if (isTerminal) {
        if (stateId === 'Release Complete') return '#10b981'; // Green
        if (stateId === 'Violation Halt') return '#ef4444'; // Red
        if (stateId === 'Blocked') return '#f59e0b'; // Amber
    }
    return '#4a90e2'; // Standard active blue
}

function updateStatusPanel() {
    if (!currentTrace) return;
    const transStr = currentTrace.transitions ? currentTrace.transitions.length : 0;
    DOM.transitions.textContent = transStr;
    DOM.terminalState.textContent = currentTrace.final_state;
    DOM.terminalState.className = 'value';
    if (currentTrace.final_state === 'Release Complete') DOM.terminalState.classList.add('status-completion');
    else if (currentTrace.final_state === 'Violation Halt') DOM.terminalState.classList.add('status-violation');
    else if (currentTrace.final_state === 'Blocked') DOM.terminalState.classList.add('status-blocked');
}

// --------------------------------
// PLAYBACK ENGINE
// --------------------------------
function setPlaybackState(state) {
    DOM.playbackStatus.textContent = state;
    if (state === 'Playing') {
        DOM.btnPlay.style.color = 'var(--accent)';
    } else {
        DOM.btnPlay.style.color = '';
    }
}

function stepAnimation() {
    if (!currentTrace || !currentTrace.transitions || currentTickIndex >= currentTrace.transitions.length) {
        pauseAnimation();
        setPlaybackState("Complete");
        diag.log("Playback completed");
        return;
    }

    const t = currentTrace.transitions[currentTickIndex];
    const fromState = norm(t.from_state);
    const toState = norm(t.to_state);
    const isLast = currentTickIndex === currentTrace.transitions.length - 1;

    // Update Log
    const logEntry = document.createElement('div');
    let logClass = 'log-ok';
    if (!t.allowed) logClass = toState === 'Blocked' ? 'log-warn' : 'log-err';
    logEntry.className = `log-entry ${logClass}`;
    logEntry.textContent = `[Tick ${t.tick}] ${fromState} → ${toState} (${t.event})`;
    DOM.log.appendChild(logEntry);
    DOM.log.scrollTop = DOM.log.scrollHeight;

    // Timeline Strips
    DOM.tick.textContent = `Tick: ${currentTickIndex + 1} / ${currentTrace.transitions.length}`;
    DOM.currentAction.textContent = `${fromState} → ${toState}`;

    // Update Graph Nodes
    if (nodesData.get(fromState)) {
        nodesData.update({ id: fromState, color: { background: '#1c1c24', border: '#4a90e2' }});
    } else {
        diag.warn(`Missing from_state node: ${fromState}`);
    }

    if (nodesData.get(toState)) {
        nodesData.update({ 
            id: toState, 
            color: { background: getNodeColor(toState, isLast), border: '#ffffff' }
        });
    } else {
        diag.warn(`Missing to_state node: ${toState}`);
    }

    // Update Edge
    const edgeIds = edgesData.getIds({ filter: e => e.from === fromState && e.to === toState });
    if (edgeIds.length > 0) {
        edgesData.update({ 
            id: edgeIds[0], 
            color: { color: getNodeColor(toState, isLast) }, 
            width: 4,
            dashes: !t.allowed
        });
    } else {
        // Dynamically inject if missing in canonical
        diag.warn(`Dynamically injecting unmapped edge: ${fromState} -> ${toState}`);
        const dynId = `dyn_${fromState}_${toState}_${currentTickIndex}`;
        dynamicallyAddedEdges.push(dynId);
        edgesData.add({
            id: dynId,
            from: fromState, to: toState, 
            color: { color: getNodeColor(toState, isLast) },
            width: 4, dashes: !t.allowed,
            smooth: { type: 'curvedCW' }
        });
    }

    currentTickIndex++;
}

function getSpeedMs() {
    const val = DOM.selSpeed.value;
    if (val === 'slow') return 1200;
    if (val === 'fast') return 300;
    return 650; // normal
}

function playAnimation() {
    if (!currentTrace) return;
    if (currentTickIndex >= (currentTrace.transitions ? currentTrace.transitions.length : 0)) {
        resetPlayback();
    }
    if (playbackInterval) clearInterval(playbackInterval);
    
    setPlaybackState("Playing");
    diag.log("Playback started");
    stepAnimation(); // do first step immediately
    
    playbackInterval = setInterval(stepAnimation, getSpeedMs());
}

function pauseAnimation() {
    if (playbackInterval) {
        clearInterval(playbackInterval);
        playbackInterval = null;
        setPlaybackState("Paused");
        diag.log("Playback paused");
    }
}

function resetPlayback() {
    pauseAnimation();
    currentTickIndex = 0;
    resetGraphVisuals();
    DOM.log.innerHTML = '';
    DOM.tick.textContent = `Tick: 0 / ${currentTrace && currentTrace.transitions ? currentTrace.transitions.length : 0}`;
    DOM.currentAction.textContent = "Ready";
    setPlaybackState("Stopped");
    
    // Clear dynamically added edges
    dynamicallyAddedEdges.forEach(id => edgesData.remove(id));
    dynamicallyAddedEdges = [];

    diag.log("Playback reset");
}

function stepForward() {
    pauseAnimation();
    stepAnimation();
}


// --------------------------------
// SCENARIO LOADING
// --------------------------------
async function loadScenario(key, config) {
    diag.log(`Loading scenario: ${key}`);
    
    // Reset UI
    document.querySelectorAll('.btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`btn-${key}`).classList.add('active');
    
    DOM.scenarioName.textContent = config.label;
    DOM.terminalState.textContent = 'Loading...';
    DOM.terminalState.className = 'value';
    
    pauseAnimation();

    try {
        const res = await fetch(config.trace);
        if (!res.ok) throw new Error(`HTTP ${res.status} on trace load`);
        currentTrace = await res.json();
        
        diag.log(`Trace loaded successfully. Transitions: ${currentTrace.transitions ? currentTrace.transitions.length : 0}`);
        
        updateStatusPanel();
        resetPlayback();

    } catch (e) {
        diag.error("Failed to load scenario trace", e);
        DOM.terminalState.textContent = 'Error loading trace';
        DOM.terminalState.style.color = 'red';
        showFallback("Unable to load trace data: " + config.trace);
        currentTrace = null;
    }
}

async function bootstrap() {
    diag.log("Bootstrapping Site Simulator");
    initGraph();

    // Hook up controls
    DOM.btnPlay.onclick = playAnimation;
    DOM.btnPause.onclick = pauseAnimation;
    DOM.btnReset.onclick = resetPlayback;
    DOM.btnStep.onclick = stepForward;
    DOM.selSpeed.onchange = () => {
        if (playbackInterval) playAnimation(); // restart interval with new speed
    };

    try {
        const res = await fetch('scenarios.json');
        if (!res.ok) throw new Error("Failed to load scenarios.json");
        const scenarios = await res.json();
        
        Object.keys(scenarios).forEach(key => {
            const btn = document.createElement('button');
            btn.className = 'btn';
            btn.id = `btn-${key}`;
            btn.textContent = scenarios[key].label;
            btn.onclick = () => loadScenario(key, scenarios[key]);
            DOM.buttons.appendChild(btn);
        });

        // Auto-load first scenario
        const firstKey = Object.keys(scenarios)[0];
        if (firstKey) {
            await loadScenario(firstKey, scenarios[firstKey]);
            // Optional: if want to auto-play on load
            // setTimeout(playAnimation, 500);
        }

    } catch (e) {
        diag.error("Failed to bootstrap scenarios", e);
        DOM.buttons.innerHTML = '<p style="color:#ef4444">Failed to load scenarios</p>';
        showFallback("Failed to load scenarios configuration.");
    }
}

document.addEventListener('DOMContentLoaded', bootstrap);
