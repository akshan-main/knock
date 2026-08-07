import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.29.4/full/pyodide.mjs";

const runtime = document.querySelector("#runtime");
const loadingNote = document.querySelector("#loading-note");
const indexURL = "https://cdn.jsdelivr.net/pyodide/v0.29.4/full/";

async function start() {
  try {
    runtime.lastChild.textContent = " starting CPython";
    const python = await loadPyodide({ indexURL });
    python.FS.mkdirTree("/app/manners");

    for (const file of ["__init__.py", "models.py", "engine.py"]) {
      const response = await fetch(`./manners/${file}`);
      if (!response.ok) throw new Error(`Could not load manners/${file}`);
      python.FS.writeFile(`/app/manners/${file}`, await response.text());
    }

    python.runPython('import sys; sys.path.insert(0, "/app")');
    const app = await fetch("./web/app.py");
    if (!app.ok) throw new Error("Could not load the browser adapter");
    await python.runPythonAsync(await app.text());
    globalThis.mannersPython = python;
  } catch (error) {
    runtime.classList.add("runtime-error");
    runtime.lastChild.textContent = " Python failed to start";
    loadingNote.textContent = `${error}. Reload to try again.`;
    const lab = document.querySelector("#lab");
    lab.dataset.ready = "error";
    lab.setAttribute("aria-busy", "false");
    document.querySelector("#decision-kind").textContent = "UNAVAILABLE";
    document.querySelector("#decision-agent").textContent = "PYTHON DID NOT START";
    document.querySelector("#decision-cue").textContent = "No simulated decision.";
    document.querySelector("#decision-reason").textContent = "Reload to retry the local runtime.";
    console.error(error);
  }
}

start();
