import { state } from './state.js';

let audioCtx = null;
let analyser = null;
let gainNode = null;
let audioSource = null;
export let freqData = null;

// Hardware DSP Equalizer Filter Nodes
let eqSubNode = null;
let eqMidNode = null;
let eqHighNode = null;
let eqPanNode = null;

export function getAudioContext() {
  return audioCtx;
}

export function getAnalyser() {
  return analyser;
}

export function initAudioContext(audioPlayerElement, onInit) {
  try {
    if (!audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      audioCtx = new AudioContextClass();
      
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      analyser.smoothingTimeConstant = 0.86;
      freqData = new Uint8Array(analyser.frequencyBinCount);

      gainNode = audioCtx.createGain();
      gainNode.gain.value = state.isMuted ? 0 : state.lastVolume;

      // 4-Band Hardware DSP Parametric Equalizer Filters
      eqSubNode = audioCtx.createBiquadFilter();
      eqSubNode.type = "lowshelf";
      eqSubNode.frequency.value = 60;
      eqSubNode.gain.value = 4.0; // Default

      eqMidNode = audioCtx.createBiquadFilter();
      eqMidNode.type = "peaking";
      eqMidNode.frequency.value = 2500;
      eqMidNode.Q.value = 1.0;
      eqMidNode.gain.value = 2.0;

      eqHighNode = audioCtx.createBiquadFilter();
      eqHighNode.type = "highshelf";
      eqHighNode.frequency.value = 10000;
      eqHighNode.gain.value = 3.0;

      if (audioCtx.createStereoPanner) {
        eqPanNode = audioCtx.createStereoPanner();
        eqPanNode.pan.value = 0.0;
      }

      // Route: audioPlayer -> audioSource -> eqSub -> eqMid -> eqHigh -> [eqPan] -> analyser -> gainNode -> destination
      audioSource = audioCtx.createMediaElementSource(audioPlayerElement);
      let curr = audioSource;
      curr.connect(eqSubNode);
      curr = eqSubNode;
      curr.connect(eqMidNode);
      curr = eqMidNode;
      curr.connect(eqHighNode);
      curr = eqHighNode;

      if (eqPanNode) {
        curr.connect(eqPanNode);
        curr = eqPanNode;
      }

      curr.connect(analyser);
      analyser.connect(gainNode);
      gainNode.connect(audioCtx.destination);

      if (onInit) onInit(true);
    }

    if (audioCtx.state === "suspended") {
      audioCtx.resume().then(() => {
        if (onInit) onInit(false, "resumed");
      });
    }
  } catch (err) {
    console.warn("Web Audio setup notice:", err);
  }
}

export function updateVolume(vol, muted) {
  if (gainNode) {
    gainNode.gain.value = muted ? 0 : vol;
  }
}

export function updateEq(type, value) {
  if (type === 'sub' && eqSubNode) eqSubNode.gain.value = value;
  if (type === 'mid' && eqMidNode) eqMidNode.gain.value = value;
  if (type === 'high' && eqHighNode) eqHighNode.gain.value = value;
  if (type === 'pan' && eqPanNode) eqPanNode.pan.value = value;
}

export function getAudioData() {
  if (analyser && freqData) {
    analyser.getByteFrequencyData(freqData);
    return freqData;
  }
  return null;
}
