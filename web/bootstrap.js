import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.29.4/full/pyodide.mjs";

const runtime = document.querySelector("#runtime");
const runtimeLabel = document.querySelector("#runtime-label");
const loadingNote = document.querySelector("#loading-note");
const indexURL = "https://cdn.jsdelivr.net/pyodide/v0.29.4/full/";
const buildID = "plain-v2";

async function start() {
  try {
    runtimeLabel.textContent = "starting the demo";
    const python = await loadPyodide({ indexURL });
    python.FS.mkdirTree("/app/manners");

    for (const file of ["__init__.py", "models.py", "engine.py"]) {
      const response = await fetch(`./manners/${file}?v=${buildID}`);
      if (!response.ok) throw new Error(`Could not load manners/${file}`);
      python.FS.writeFile(`/app/manners/${file}`, await response.text());
    }

    python.runPython('import sys; sys.path.insert(0, "/app")');
    const app = await fetch(`./web/app.py?v=${buildID}`);
    if (!app.ok) throw new Error("Could not load the browser adapter");
    await python.runPythonAsync(await app.text());
    globalThis.mannersPython = python;
  } catch (error) {
    runtime.classList.add("runtime-error");
    runtimeLabel.textContent = "demo unavailable";
    loadingNote.textContent = `${error}. Reload to try again.`;
    const lab = document.querySelector("#lab");
    lab.dataset.ready = "error";
    lab.setAttribute("aria-busy", "false");
    document.querySelector("#decision-kind").textContent = "UNAVAILABLE";
    document.querySelector("#decision-agent").textContent = "THE EXAMPLE DID NOT START";
    document.querySelector("#decision-cue").textContent = "Nothing is being simulated.";
    document.querySelector("#decision-reason").textContent = "Reload the page to try again.";
    console.error(error);
  }
}

start();
