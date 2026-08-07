const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.29.4/full/";
const BUILD_ID = "knock-v4";
const PYTHON_FILES = ["__init__.py", "audio.py", "features.py", "learner.py", "detector.py"];

const runtime = document.querySelector("#runtime");
const runtimeLabel = document.querySelector("#runtime-label");
const micState = document.querySelector("#mic-state");
const enableButton = document.querySelector("#enable-mic");
const fileWarning = document.querySelector("#file-warning");
const canvas = document.querySelector("#waveform");
const canvasContext = canvas?.getContext("2d");

function setRuntime(kind, label) {
  runtime?.setAttribute("data-state", kind);
  if (runtimeLabel) runtimeLabel.textContent = label;
}

function drawWaveform(samples) {
  if (!canvas || !canvasContext) return;
  const ratio = Math.max(1, Math.floor(window.devicePixelRatio || 1));
  const width = Math.max(1, canvas.clientWidth * ratio);
  const height = Math.max(1, canvas.clientHeight * ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  const style = getComputedStyle(document.documentElement);
  const background = style.getPropertyValue("--ink").trim() || "#171812";
  const signal = style.getPropertyValue("--acid").trim() || "#d9ff43";
  canvasContext.fillStyle = background;
  canvasContext.fillRect(0, 0, width, height);
  canvasContext.strokeStyle = signal;
  canvasContext.lineWidth = Math.max(1.2, ratio * 1.1);
  canvasContext.beginPath();

  const stride = Math.max(1, Math.floor(samples.length / width));
  for (let x = 0; x < width; x += 1) {
    const sample = samples[Math.min(samples.length - 1, x * stride)] || 0;
    const y = height / 2 + sample * height * 2.4;
    if (x === 0) canvasContext.moveTo(x, y);
    else canvasContext.lineTo(x, y);
  }
  canvasContext.stroke();
}

class AudioBridge {
  constructor() {
    this.context = null;
    this.stream = null;
    this.source = null;
    this.processor = null;
    this.silentGain = null;
    this.sampleRate = 0;
    this.started = false;
  }

  async start() {
    if (this.started) {
      await this.context?.resume();
      return this.sampleRate;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("This browser does not expose microphone capture.");
    }

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
      video: false,
    });

    const AudioContext = window.AudioContext || window.webkitAudioContext;
    this.context = new AudioContext({ latencyHint: "interactive" });
    this.sampleRate = this.context.sampleRate;
    await this.context.audioWorklet.addModule(`./web/audio-worklet.js?v=${BUILD_ID}`);

    this.source = this.context.createMediaStreamSource(this.stream);
    this.processor = new AudioWorkletNode(this.context, "knock-pcm-processor", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
    });
    this.silentGain = this.context.createGain();
    this.silentGain.gain.value = 0;

    this.processor.port.onmessage = (event) => {
      const frame = new Float32Array(event.data.pcm);
      drawWaveform(frame);
      if (window.knockFrameProxy) window.knockFrameProxy(frame);
    };

    this.source.connect(this.processor);
    this.processor.connect(this.silentGain);
    this.silentGain.connect(this.context.destination);
    await this.context.resume();
    this.started = true;
    return this.sampleRate;
  }

  stop() {
    for (const track of this.stream?.getTracks() || []) track.stop();
    this.context?.close();
    this.started = false;
  }
}

window.knockAudio = new AudioBridge();

function setupMotion() {
  if (!window.gsap) return;
  const gsap = window.gsap;
  if (window.ScrollTrigger) gsap.registerPlugin(window.ScrollTrigger);

  gsap.from(".hero-copy > *", {
    opacity: 0,
    y: 28,
    duration: 0.9,
    stagger: 0.09,
    ease: "power3.out",
  });
  gsap.from(".hero-signal", {
    opacity: 0,
    scale: 0.82,
    rotate: 4,
    duration: 1.15,
    ease: "power3.out",
  });

  if (window.ScrollTrigger) {
    gsap.fromTo(
      ".technical-intro",
      { scale: 0.82, opacity: 0.35 },
      {
        scale: 1,
        opacity: 1,
        ease: "none",
        scrollTrigger: {
          trigger: ".technical",
          start: "top 85%",
          end: "center 45%",
          scrub: true,
        },
      },
    );

    document.querySelectorAll(".example-card").forEach((card, index) => {
      gsap.set(card, { y: index * 8, rotate: (index - 1) * 0.7 });
    });
  }
}

async function loadPython() {
  setRuntime("loading", "preparing detector");
  const { loadPyodide } = await import(`${PYODIDE_URL}pyodide.mjs`);
  const python = await loadPyodide({ indexURL: PYODIDE_URL });
  await python.loadPackage("numpy");
  python.FS.mkdirTree("/app/knock");

  for (const filename of PYTHON_FILES) {
    const response = await fetch(`./knock/${filename}?v=${BUILD_ID}`);
    if (!response.ok) throw new Error(`Could not load knock/${filename}`);
    python.FS.writeFile(`/app/knock/${filename}`, await response.text());
  }

  python.runPython('import sys; sys.path.insert(0, "/app")');
  const adapter = await fetch(`./web/app.py?v=${BUILD_ID}`);
  if (!adapter.ok) throw new Error("Could not load the browser adapter.");
  await python.runPythonAsync(await adapter.text());
  window.knockPython = python;
  setRuntime("ready", "detector ready");
}

async function start() {
  setupMotion();
  if (window.location.protocol === "file:") {
    if (fileWarning) fileWarning.hidden = false;
    setRuntime("error", "open the secure live site");
    if (micState) micState.textContent = "Microphone training needs the HTTPS version linked above.";
    if (enableButton) enableButton.disabled = true;
    return;
  }
  try {
    await loadPython();
  } catch (error) {
    console.error(error);
    setRuntime("error", "detector unavailable");
    if (micState) micState.textContent = "KNOCK did not start. Reload to try again.";
    if (enableButton) enableButton.disabled = true;
  }
}

window.addEventListener("beforeunload", () => window.knockAudio.stop());
start();
