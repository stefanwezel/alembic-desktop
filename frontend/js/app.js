const API_BASE = "http://localhost:3001";

// ─── Icons ────────────────────────────────────────────────────────────────────

function icon(name, size = 16) {
  const icons = {
    plus: `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 16 16" fill="currentColor"><path d="M8 2a1 1 0 011 1v4h4a1 1 0 110 2H9v4a1 1 0 11-2 0V9H3a1 1 0 010-2h4V3a1 1 0 011-1z"/></svg>`,
    edit: `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 16 16" fill="currentColor"><path d="M11.5 1.5a1.5 1.5 0 012.12 2.12L5.83 11.4l-2.83.71.71-2.83L11.5 1.5zM2 13.5h12a.5.5 0 010 1H2a.5.5 0 010-1z"/></svg>`,
    play: `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 16 16" fill="currentColor"><path d="M4 2.5a.5.5 0 01.77-.42l9 5.5a.5.5 0 010 .84l-9 5.5A.5.5 0 014 13.5v-11z"/></svg>`,
    export: `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 16 16" fill="currentColor"><path d="M8.75 1a.75.75 0 00-1.5 0v6.59L5.3 5.64a.75.75 0 00-1.1 1.02l3.25 3.5a.75.75 0 001.1 0l3.25-3.5a.75.75 0 00-1.1-1.02L8.75 7.59V1zM1.75 9a.75.75 0 00-.75.75v3.5c0 .966.784 1.75 1.75 1.75h10.5A1.75 1.75 0 0015 13.25v-3.5a.75.75 0 00-1.5 0v3.5a.25.25 0 01-.25.25H2.75a.25.25 0 01-.25-.25v-3.5A.75.75 0 001.75 9z"/></svg>`,
    trash: `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 16 16" fill="currentColor"><path d="M5.5 1a.5.5 0 00-.5.5V2H2.5a.5.5 0 000 1h.5l.7 10.5a1.5 1.5 0 001.49 1.5h5.62a1.5 1.5 0 001.49-1.5L13 3h.5a.5.5 0 000-1H11v-.5a.5.5 0 00-.5-.5h-5zM6 2V1.5h4V2H6zm-2 1h8l-.7 10.5a.5.5 0 01-.49.5H5.19a.5.5 0 01-.49-.5L4 3z"/></svg>`,
    check: `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 16 16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/></svg>`,
    "chevron-left": `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 16 16" fill="currentColor"><path d="M10.35 3.15a.5.5 0 010 .7L6.21 8l4.14 4.15a.5.5 0 01-.7.7l-4.5-4.5a.5.5 0 010-.7l4.5-4.5a.5.5 0 01.7 0z"/></svg>`,
    "chevron-right": `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 16 16" fill="currentColor"><path d="M5.65 3.15a.5.5 0 01.7 0l4.5 4.5a.5.5 0 010 .7l-4.5 4.5a.5.5 0 01-.7-.7L9.79 8 5.65 3.85a.5.5 0 010-.7z"/></svg>`,
  };
  return icons[name] || "";
}

// ─── View Management ───────────────────────────────────────────────────────────

function showView(name) {
  document.querySelectorAll("section[id^='view-']").forEach((s) => {
    s.style.display = "none";
  });
  document.getElementById(`view-${name}`).style.display = "block";
}

// ─── State ─────────────────────────────────────────────────────────────────────

let currentSessionId = null;
let currentIdLeft = null;
let currentIdRight = null;

// ─── Overview ──────────────────────────────────────────────────────────────────

async function loadOverview() {
  showView("overview");
  try {
    const res = await fetch(`${API_BASE}/overview`);
    const data = await res.json();
    renderOverview(data);
  } catch (e) {
    console.error("Error loading overview:", e);
  }
}

function renderOverview(data) {
  const container = document.getElementById("sessions-list");
  container.innerHTML = "";

  // New session button
  const newDiv = document.createElement("div");
  newDiv.className = "session-container";
  const newBtn = document.createElement("button");
  newBtn.className = "new-session-button";
  newBtn.innerHTML = icon("plus") + " New session";
  newBtn.addEventListener("click", () => newSession());
  newDiv.appendChild(newBtn);
  container.appendChild(newDiv);

  for (const session of data.sessions) {
    const div = document.createElement("div");
    div.className = "session-container";

    let thumbnailsHtml = "";
    for (const thumbId of session.thumbnails || []) {
      thumbnailsHtml += `<img src="${API_BASE}/serve_image?img_id=${thumbId}&version=thumbnail" alt="Thumbnail" class="thumbnail-img" />`;
    }

    div.innerHTML = `
      <div class="session-content">
        ${thumbnailsHtml}
        <div class="session-progress">
          <span id="sessionName${session.id}">${escapeHtml(session.name)}</span>
          <button class="rename-session-button" data-action="rename" data-session-id="${session.id}">${icon("edit", 14)}</button>
        </div>
        <div class="session-progress">
          <span>Reviewed:</span>
          <progress id="progressBar${session.id}" value="${session.progress}" max="100"></progress>
        </div>
        <div class="session-actions">
          <button class="open-session-button" id="openSessionButton${session.id}"
            data-action="open" data-session-id="${session.id}" data-progress="${session.progress}">${icon("play")} Resume</button>
          <button class="download-button" id="downloadButton${session.id}"
            data-action="download" data-session-id="${session.id}" data-session-name="${escapeHtml(session.name)}">${icon("export")} Export</button>
          <button class="drop-session-button" id="dropSessionButton${session.id}"
            data-action="drop" data-session-id="${session.id}">${icon("trash")} Drop</button>
        </div>
      </div>
    `;
    container.appendChild(div);

    div.querySelector('[data-action="rename"]').addEventListener("click", () => renameSession(session.id));
    div.querySelector('[data-action="open"]').addEventListener("click", () => openSession(session.id, session.progress));
    div.querySelector('[data-action="download"]').addEventListener("click", () => downloadSession(session.id, session.name));
    div.querySelector('[data-action="drop"]').addEventListener("click", () => dropSession(session.id));

    if (session.progress >= 100) {
      document.getElementById(`progressBar${session.id}`).classList.add("complete");
    }

    checkDownloadStatus(session.id, session.progress);
  }
}

async function checkDownloadStatus(sessionId, progress) {
  try {
    const res = await fetch(`${API_BASE}/has_been_downloaded?session_id=${sessionId}`);
    if (!res.ok) return;
    const data = await res.json();
    const downloaded = data.has_been_downloaded;
    const downloadBtn = document.getElementById(`downloadButton${sessionId}`);
    const dropBtn = document.getElementById(`dropSessionButton${sessionId}`);
    const openBtn = document.getElementById(`openSessionButton${sessionId}`);

    if (progress >= 100) {
      if (downloaded) {
        dropBtn && dropBtn.classList.add("complete");
        downloadBtn && downloadBtn.classList.remove("complete");
      } else {
        downloadBtn && downloadBtn.classList.add("complete");
      }
    } else {
      openBtn && openBtn.classList.add("complete");
    }
  } catch (e) {
    console.error("Error checking download status:", e);
  }
}

function newSession() {
  document.getElementById("directory-path").value = "";
  document.getElementById("upload-overlay").style.visibility = "hidden";
  document.getElementById("spinner").style.visibility = "hidden";
  showView("upload");

  // In Tauri, show a "Browse" button and hide the text input
  const browseBtn = document.getElementById("browse-button");
  const dirInput = document.getElementById("directory-path");
  if (window.__TAURI__) {
    dirInput.readOnly = true;
    dirInput.placeholder = "Click Browse to select a folder";
    if (browseBtn) browseBtn.style.display = "";
  } else {
    if (browseBtn) browseBtn.style.display = "none";
  }
}

async function browseDirectory() {
  if (!window.__TAURI__) return;
  const { open } = window.__TAURI__.dialog;
  const selected = await open({ directory: true, multiple: false, title: "Select image folder" });
  if (selected) {
    document.getElementById("directory-path").value = selected;
  }
}

async function openSession(sessionId, progress) {
  if (progress >= 100) {
    showView("completed");
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/open_session?session_id=${sessionId}`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    loadDecision(sessionId, String(data.img_id_left), String(data.img_id_right));
  } catch (e) {
    console.error("Error opening session:", e);
  }
}

async function downloadSession(sessionId, sessionName) {
  const btn = document.getElementById(`downloadButton${sessionId}`);
  btn.disabled = true;
  btn.innerHTML = "Preparing...";
  btn.classList.add("loading");
  try {
    const res = await fetch(`${API_BASE}/download?session_id=${sessionId}`);
    if (!res.ok) throw new Error("Download failed!");
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${sessionName}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    setTimeout(() => loadOverview(), 2000);
  } catch (e) {
    console.error("Download failed:", e);
    btn.disabled = false;
    btn.innerHTML = icon("export") + " Export";
    btn.classList.remove("loading");
  }
}

async function dropSession(sessionId) {
  try {
    await fetch(`${API_BASE}/drop_session/${sessionId}`);
    loadOverview();
  } catch (e) {
    console.error("Error dropping session:", e);
  }
}

function renameSession(sessionId) {
  if (document.querySelector(".popup-overlay")) return;
  const overlay = document.createElement("div");
  overlay.className = "popup-overlay";
  const popup = document.createElement("div");
  popup.className = "popup-container";
  const currentName = document.getElementById(`sessionName${sessionId}`).innerText;
  popup.innerHTML = `
    <h3>Rename Session</h3>
    <input type="text" id="newSessionName" placeholder="Enter new name" value="${escapeHtml(currentName)}">
    <div class="popup-buttons">
      <button class="cancel" id="popup-cancel">Cancel</button>
      <button id="popup-save">Save</button>
    </div>
  `;
  overlay.appendChild(popup);
  document.body.appendChild(overlay);
  document.getElementById("popup-cancel").addEventListener("click", () => closePopup());
  document.getElementById("popup-save").addEventListener("click", () => submitNewSessionName(sessionId));
  const inputField = document.getElementById("newSessionName");
  inputField.focus();
  inputField.setSelectionRange(currentName.length, currentName.length);
  inputField.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      submitNewSessionName(sessionId);
    }
  });
}

function closePopup() {
  const overlay = document.querySelector(".popup-overlay");
  if (overlay) overlay.remove();
}

async function submitNewSessionName(sessionId) {
  const nameInput = document.getElementById("newSessionName");
  const newName = nameInput ? nameInput.value.trim() : "";
  if (!newName) return;
  try {
    const res = await fetch(`${API_BASE}/rename_session/${sessionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_name: newName }),
    });
    if (res.ok) {
      closePopup();
      loadOverview();
    } else {
      alert("Error renaming session.");
    }
  } catch (e) {
    console.error("Error:", e);
    alert("Error renaming session.");
  }
}

// ─── Upload ────────────────────────────────────────────────────────────────────

let isProcessing = false;

async function createSessionFromDirectory() {
  const dir = document.getElementById("directory-path").value.trim();
  if (!dir) {
    alert("Please enter a directory path.");
    return;
  }

  const overlay = document.getElementById("upload-overlay");
  const progressText = document.getElementById("progress-text");
  const spinner = document.getElementById("spinner");

  isProcessing = true;
  overlay.style.visibility = "visible";
  spinner.style.visibility = "visible";
  progressText.textContent = "Processing images...";

  try {
    const res = await fetch(`${API_BASE}/create_session_from_directory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ directory: dir }),
    });
    if (!res.ok) {
      const err = await res.json();
      alert(`Error: ${err.error || "Failed to create session."}`);
      return;
    }
    loadOverview();
  } catch (e) {
    console.error("Error creating session from directory:", e);
    alert("Error creating session. Please try again.");
  } finally {
    isProcessing = false;
    overlay.style.visibility = "hidden";
    spinner.style.visibility = "hidden";
  }
}

window.addEventListener("beforeunload", (event) => {
  if (isProcessing) {
    event.preventDefault();
    event.returnValue = "Processing is in progress. If you leave, progress will be lost.";
  }
});

// ─── Decision ──────────────────────────────────────────────────────────────────

let decisionKeydownHandlers = [];

function clearDecisionHandlers() {
  for (const handler of decisionKeydownHandlers) {
    document.removeEventListener("keydown", handler);
  }
  decisionKeydownHandlers = [];
}

function loadDecision(sessionId, idLeft, idRight) {
  currentSessionId = sessionId;
  currentIdLeft = idLeft;
  currentIdRight = idRight;

  showView("decision");

  // Reset image transforms and src
  const leftImg = document.getElementById("img-left");
  const rightImg = document.getElementById("img-right");
  leftImg.style.transform = "scale(1) translate(0px, 0px)";
  leftImg.src = "";
  rightImg.style.transform = "scale(1) translate(0px, 0px)";
  rightImg.src = "";

  // Remove old buttons
  document.querySelector(".img-wrapper:not(.right)").querySelectorAll("button").forEach((b) => b.remove());
  document.querySelector(".img-wrapper.right").querySelectorAll("button").forEach((b) => b.remove());

  // Clear old keyboard handlers
  clearDecisionHandlers();

  // Load images
  renderImage("left", idLeft);
  renderImage("right", idRight);

  // Setup controls for each side
  setupImageControls("left", leftImg, idLeft, idRight);
  setupImageControls("right", rightImg, idRight, idLeft);

  // R key resets zoom on both images
  const resetHandler = (event) => {
    if (event.code === "KeyR") {
      leftImg.style.transform = "scale(1) translate(0px, 0px)";
      rightImg.style.transform = "scale(1) translate(0px, 0px)";
    }
  };
  document.addEventListener("keydown", resetHandler);
  decisionKeydownHandlers.push(resetHandler);
}

function setupImageControls(side, img, clickedId, otherId) {
  const wrapper = img.parentElement;

  // Per-image pan/zoom state
  const state = { scale: 1, panX: 0, panY: 0, lastX: 0, lastY: 0, isPanning: false };

  // Reset Zoom button
  const resetButton = document.createElement("button");
  resetButton.textContent = "Reset Zoom";
  resetButton.classList.add("reset-button");
  wrapper.appendChild(resetButton);
  resetButton.onclick = () => {
    state.scale = 1;
    state.panX = 0;
    state.panY = 0;
    img.style.transform = `scale(${state.scale}) translate(${state.panX}px, ${state.panY}px)`;
  };

  // Like button (💜)
  const selectButtonLike = document.createElement("button");
  selectButtonLike.innerHTML = icon("check", 20);
  selectButtonLike.classList.add("select-button-top");
  wrapper.appendChild(selectButtonLike);
  selectButtonLike.onclick = () => {
    updateImages(`${API_BASE}/like_image`, currentSessionId, side, clickedId, otherId);
    animateButton(selectButtonLike);
  };

  // Continue from button (⬅️ / ➡️)
  const selectButtonContinueFrom = document.createElement("button");
  selectButtonContinueFrom.classList.add("select-button-side");
  if (side === "left") {
    selectButtonContinueFrom.classList.add("left-side");
    selectButtonContinueFrom.innerHTML = icon("chevron-left", 20);
  } else {
    selectButtonContinueFrom.classList.add("right-side");
    selectButtonContinueFrom.innerHTML = icon("chevron-right", 20);
  }
  wrapper.appendChild(selectButtonContinueFrom);
  selectButtonContinueFrom.onclick = () => {
    updateImages(`${API_BASE}/continue_from`, currentSessionId, side, clickedId, otherId);
    animateButton(selectButtonContinueFrom);
  };

  // Drop button (🗑️)
  const selectButtonDrop = document.createElement("button");
  selectButtonDrop.innerHTML = icon("trash", 20);
  selectButtonDrop.classList.add("select-button-bottom");
  wrapper.appendChild(selectButtonDrop);
  selectButtonDrop.onclick = () => {
    updateImages(`${API_BASE}/drop_image`, currentSessionId, side, clickedId, otherId);
    animateButton(selectButtonDrop);
  };

  // Keyboard shortcuts
  const keyHandler = (event) => {
    if (side === "left") {
      if (event.code === "KeyD") selectButtonLike.click();
      else if (event.code === "KeyS") selectButtonContinueFrom.click();
      else if (event.code === "KeyF") selectButtonDrop.click();
    } else {
      if (event.code === "KeyK") selectButtonLike.click();
      else if (event.code === "KeyL") selectButtonContinueFrom.click();
      else if (event.code === "KeyJ") selectButtonDrop.click();
    }
  };
  document.addEventListener("keydown", keyHandler);
  decisionKeydownHandlers.push(keyHandler);

  // Zoom on mouse wheel
  img.onwheel = (e) => {
    e.preventDefault();
    state.scale += e.deltaY * -0.001;
    state.scale = Math.min(Math.max(0.125, state.scale), 4);
    img.style.transform = `scale(${state.scale}) translate(${state.panX}px, ${state.panY}px)`;
  };

  // Pan on drag
  img.onmousedown = (e) => {
    e.preventDefault();
    img.classList.add("grabbing");
    state.lastX = e.clientX - state.panX;
    state.lastY = e.clientY - state.panY;
    state.isPanning = true;
  };
  img.onmousemove = (e) => {
    if (state.isPanning) {
      e.preventDefault();
      state.panX = e.clientX - state.lastX;
      state.panY = e.clientY - state.lastY;
      requestAnimationFrame(() => {
        img.style.transform = `scale(${state.scale}) translate(${state.panX}px, ${state.panY}px)`;
      });
    }
  };
  img.onmouseup = () => {
    img.classList.remove("grabbing");
    state.isPanning = false;
  };
}

async function renderImage(side, imgId) {
  const img = document.getElementById(`img-${side}`);

  try {
    const thumbnailResponse = await fetch(`${API_BASE}/serve_image?img_id=${imgId}&version=thumbnail`);
    if (!thumbnailResponse.ok || thumbnailResponse.headers.get("Content-Type") !== "image/jpeg") {
      throw new Error("Invalid response or no thumbnail image found");
    }
    const thumbnailBlob = await thumbnailResponse.blob();
    const thumbnailURL = URL.createObjectURL(thumbnailBlob);
    img.src = thumbnailURL;

    img.onload = async () => {
      console.log("Thumbnail image loaded successfully.");

      const previewResponse = await fetch(`${API_BASE}/serve_image?img_id=${imgId}&version=preview`);
      if (!previewResponse.ok || previewResponse.headers.get("Content-Type") !== "image/jpeg") {
        throw new Error("Invalid response or no preview image found");
      }
      const previewBlob = await previewResponse.blob();
      const previewURL = URL.createObjectURL(previewBlob);

      img.onload = async () => {
        console.log("Preview image loaded successfully.");
        URL.revokeObjectURL(thumbnailURL);

        const displayResponse = await fetch(`${API_BASE}/serve_image?img_id=${imgId}&version=display`);
        if (displayResponse.ok) {
          console.log("Trying to render display image...");
          const displayBlob = await displayResponse.blob();
          const displayURL = URL.createObjectURL(displayBlob);

          img.onload = () => {
            console.log("Display image loaded successfully.");
            URL.revokeObjectURL(previewURL);
          };
          img.src = displayURL;
        }
      };

      img.src = previewURL;
    };
  } catch (error) {
    if (error.name === "AbortError") {
      console.warn(`Fetch aborted for ${imgId}, but continuing...`);
    } else {
      console.error(`Error rendering image for ${imgId}:`, error);
      img.parentElement.innerHTML = `
        <div class="not-found">
          <p>No more images found. Looks like you're done!<br>
          <span class="small-text">Decide what you want to do with the last image to complete the session.</span></p>
        </div>
      `;
    }
  }
}

async function updateImages(route, sessionId, position, clickedImageId, otherImageId) {
  try {
    const res = await fetch(route, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        position: position,
        clickedImageId: clickedImageId,
        otherImageId: otherImageId,
      }),
    });
    if (!res.ok) {
      console.error(`API error: ${res.status}`);
      return;
    }
    const data = await res.json();
    if (!data.redirect) {
      console.log("No redirect provided.");
      return;
    }
    if (data.redirect === "completed" || data.redirect === "/completed") {
      showView("completed");
    } else {
      // data.redirect is "/sweep?session_id=...&id_left=...&id_right=..."
      // Fetch /sweep to persist last_viewed, then use the returned IDs
      const sweepRes = await fetch(`${API_BASE}${data.redirect}`);
      const sweepData = await sweepRes.json();
      loadDecision(
        String(sweepData.session_id),
        String(sweepData.img_id_left),
        String(sweepData.img_id_right)
      );
    }
  } catch (e) {
    console.error("Error:", e);
  }
}

function animateButton(button) {
  button.classList.add("pop-up");
  setTimeout(() => button.classList.remove("pop-up"), 300);
}

function pauseSession() {
  showView("overview");
  loadOverview();
}

// ─── Utilities ─────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ─── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("browse-button").addEventListener("click", () => browseDirectory());
  document.getElementById("load-images-button").addEventListener("click", () => createSessionFromDirectory());
  document.getElementById("pause-session-button").addEventListener("click", () => pauseSession());
  document.getElementById("return-overview-button").addEventListener("click", () => { showView("overview"); loadOverview(); });
  loadOverview();
});
