const state = {
  sessionId: crypto.randomUUID(),
  payload: null,
  file: null,
};

const elements = {
  apiKey: document.querySelector("#apiKey"),
  saveKey: document.querySelector("#saveKey"),
  clientName: document.querySelector("#clientName"),
  pdfFile: document.querySelector("#pdfFile"),
  dropZone: document.querySelector("#dropZone"),
  fileName: document.querySelector("#fileName"),
  consent: document.querySelector("#consent"),
  startReview: document.querySelector("#startReview"),
  statusDot: document.querySelector("#statusDot"),
  statusTitle: document.querySelector("#statusTitle"),
  statusText: document.querySelector("#statusText"),
  docType: document.querySelector("#docType"),
  charCount: document.querySelector("#charCount"),
  draftPane: document.querySelector("#draftPane"),
  checklistPane: document.querySelector("#checklistPane"),
  chatMessages: document.querySelector("#chatMessages"),
  chatForm: document.querySelector("#chatForm"),
  chatInput: document.querySelector("#chatInput"),
  sendChat: document.querySelector("#sendChat"),
  copyDraft: document.querySelector("#copyDraft"),
  downloadDraft: document.querySelector("#downloadDraft"),
};

function loadApiKey() {
  const savedKey = localStorage.getItem("ca_agent_api_key") || "";
  elements.apiKey.value = savedKey;
}

function setStatus(kind, title, text) {
  elements.statusDot.className = `status-dot ${kind || ""}`;
  elements.statusTitle.textContent = title;
  elements.statusText.textContent = text;
}

function apiKey() {
  return elements.apiKey.value.trim();
}

function requireReadyForUpload() {
  if (!apiKey()) {
    throw new Error("Enter and save the backend API key first.");
  }
  if (!elements.clientName.value.trim()) {
    throw new Error("Enter the client name.");
  }
  if (!state.file) {
    throw new Error("Upload a PDF file.");
  }
  if (!elements.consent.checked) {
    throw new Error("Consent is required before sending extracted text to Groq.");
  }
}

async function parseError(response) {
  try {
    const payload = await response.json();
    return payload.detail || "Request failed.";
  } catch {
    return await response.text() || "Request failed.";
  }
}

async function postAgent(formData) {
  const response = await fetch("/agent/message", {
    method: "POST",
    headers: { "X-API-Key": apiKey() },
    body: formData,
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

function formatDocType(docType) {
  const labels = {
    form_26as: "Form 26AS",
    tax_notice: "Income Tax Notice",
    itr_summary: "ITR Summary",
    unknown: "Unknown",
  };
  return labels[docType] || docType || "Unknown";
}

function textOrEmpty(value, fallback) {
  return value && value.trim() ? value : fallback;
}

function renderPayload(payload) {
  state.payload = payload;
  elements.docType.textContent = formatDocType(payload.doc_type);
  elements.charCount.textContent = `${payload.char_count || 0} chars`;
  elements.draftPane.textContent = textOrEmpty(payload.draft, "No draft returned.");
  elements.checklistPane.textContent = textOrEmpty(payload.checklist, "No checklist returned.");
  elements.chatInput.disabled = false;
  elements.sendChat.disabled = false;
  elements.copyDraft.disabled = !payload.draft;
  elements.downloadDraft.disabled = !payload.draft;
}

function appendMessage(role, content) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  const label = document.createElement("div");
  label.className = "message-role";
  label.textContent = role === "user" ? "You" : "Agent";
  const body = document.createElement("div");
  body.textContent = content;
  node.append(label, body);
  elements.chatMessages.append(node);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function setFile(file) {
  if (!file) {
    return;
  }
  state.file = file;
  elements.fileName.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
}

async function startReview() {
  try {
    requireReadyForUpload();
    setStatus("", "Working", "Analyzing PDF and generating draft.");
    elements.startReview.disabled = true;

    const formData = new FormData();
    formData.append("session_id", state.sessionId);
    formData.append("client_name", elements.clientName.value.trim());
    formData.append("message", "Please analyze this document and prepare a draft.");
    formData.append("consent", "true");
    formData.append("file", state.file);

    const payload = await postAgent(formData);
    renderPayload(payload);
    elements.chatMessages.innerHTML = "";
    appendMessage("assistant", payload.assistant_message || "Draft and checklist are ready for CA review.");
    setStatus("good", "Draft ready", "Review the draft and checklist before client use.");
  } catch (error) {
    setStatus("error", "Action needed", error.message);
  } finally {
    elements.startReview.disabled = false;
  }
}

async function sendRevision(event) {
  event.preventDefault();
  const message = elements.chatInput.value.trim();
  if (!message) {
    return;
  }

  try {
    appendMessage("user", message);
    elements.chatInput.value = "";
    elements.chatInput.disabled = true;
    elements.sendChat.disabled = true;
    setStatus("", "Working", "Revising the draft.");

    const formData = new FormData();
    formData.append("session_id", state.sessionId);
    formData.append("message", message);

    const payload = await postAgent(formData);
    renderPayload(payload);
    appendMessage("assistant", payload.assistant_message || "Draft revised for CA review.");
    setStatus("good", "Draft revised", "Review the updated draft.");
  } catch (error) {
    appendMessage("assistant", error.message);
    setStatus("error", "Revision failed", error.message);
  } finally {
    elements.chatInput.disabled = !state.payload;
    elements.sendChat.disabled = !state.payload;
  }
}

function copyDraft() {
  if (!state.payload?.draft) {
    return;
  }
  navigator.clipboard.writeText(state.payload.draft);
  setStatus("good", "Copied", "Draft copied to clipboard.");
}

function downloadDraft() {
  if (!state.payload?.draft) {
    return;
  }
  const blob = new Blob([state.payload.draft], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "ca-draft-letter.txt";
  link.click();
  URL.revokeObjectURL(url);
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".text-surface").forEach((pane) => pane.classList.remove("active"));
      tab.classList.add("active");
      document.querySelector(`#${tab.dataset.tab}Pane`).classList.add("active");
    });
  });
}

function setupDropZone() {
  elements.pdfFile.addEventListener("change", () => setFile(elements.pdfFile.files[0]));
  ["dragenter", "dragover"].forEach((eventName) => {
    elements.dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropZone.classList.add("drag-over");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    elements.dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropZone.classList.remove("drag-over");
    });
  });
  elements.dropZone.addEventListener("drop", (event) => {
    setFile(event.dataTransfer.files[0]);
  });
}

elements.saveKey.addEventListener("click", () => {
  localStorage.setItem("ca_agent_api_key", apiKey());
  setStatus("good", "Key saved", "Backend API key saved in this browser.");
});
elements.startReview.addEventListener("click", startReview);
elements.chatForm.addEventListener("submit", sendRevision);
elements.copyDraft.addEventListener("click", copyDraft);
elements.downloadDraft.addEventListener("click", downloadDraft);

loadApiKey();
setupTabs();
setupDropZone();
