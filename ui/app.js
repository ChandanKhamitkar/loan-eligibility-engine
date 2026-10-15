const STEPS = ["uploaded", "processing", "processed", "matching", "matched", "notified"];
// Poll gently, then give up and offer a manual refresh: about 1m45s in total
const POLL_START_MS = 1500;
const POLL_MAX_MS = 5000;
const POLL_GROWTH = 1.15;
const MAX_POLLS = 25;

const form = document.getElementById("upload-form");
const fileInput = document.getElementById("file");
const fileLabel = document.getElementById("file-label");
const submit = document.getElementById("submit");
const statusBox = document.getElementById("status");
const counts = document.getElementById("counts");
const message = document.getElementById("message");
const refresh = document.getElementById("refresh");

let lastUploadId = null;

fileInput.addEventListener("change", () => {
  fileLabel.textContent = fileInput.files[0]?.name ?? "Choose a CSV file";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  submit.disabled = true;
  statusBox.hidden = false;
  refresh.hidden = true;
  lastUploadId = null;
  setMessage("Requesting upload link…");
  try {
    const { upload_id, url, fields } = await requestUpload(file.name);
    lastUploadId = upload_id;
    setMessage("Uploading…");
    await sendToStorage(url, fields, file);
    await poll(upload_id);
  } catch (error) {
    setMessage(error.message, true);
    refresh.hidden = lastUploadId === null;
  } finally {
    submit.disabled = false;
  }
});

refresh.addEventListener("click", async () => {
  refresh.hidden = true;
  try {
    await poll(lastUploadId);
  } catch (error) {
    setMessage(error.message, true);
    refresh.hidden = false;
  }
});

async function requestUpload(filename) {
  const response = await fetch("/uploads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error ?? "Could not start upload");
  return body;
}

async function sendToStorage(url, fields, file) {
  const data = new FormData();
  Object.entries(fields).forEach(([key, value]) => data.append(key, value));
  data.append("file", file);
  const response = await fetch(url, { method: "POST", body: data });
  if (!response.ok) throw new Error("Upload to storage failed");
}

async function poll(uploadId) {
  let delay = POLL_START_MS;
  for (let attempt = 1; attempt <= MAX_POLLS; attempt++) {
    const upload = await fetchStatus(uploadId);
    render(upload);
    if (upload.status === "failed") throw new Error(upload.error ?? "Processing failed");
    if (upload.status === "notified") return setMessage("Done. Check the test inbox.");
    await new Promise((resolve) => setTimeout(resolve, delay));
    delay = Math.min(delay * POLL_GROWTH, POLL_MAX_MS);
  }
  refresh.hidden = false;
  setMessage("Still working. Press refresh to check again.");
}

async function fetchStatus(uploadId) {
  const response = await fetch(`/uploads/${uploadId}`);
  if (!response.ok) throw new Error("Could not read the upload status");
  return response.json();
}

function render(upload) {
  const reached = STEPS.indexOf(upload.status);
  document.querySelectorAll("#steps li").forEach((item, index) => {
    item.classList.toggle("done", index < reached);
    item.classList.toggle("current", index === reached);
  });
  counts.replaceChildren(
    ...[
      ["Rows", upload.rows_total],
      ["Valid", upload.rows_ok],
      ["Rejected", upload.rows_rejected],
    ].flatMap(([label, value]) => {
      const term = document.createElement("dt");
      const detail = document.createElement("dd");
      term.textContent = label;
      detail.textContent = value;
      return [term, detail];
    }),
  );
  setMessage(upload.rejected_samples?.length
    ? `First rejections: ${upload.rejected_samples.map((r) => `line ${r.line_no} (${r.reason})`).join("; ")}`
    : `Status: ${upload.status}`);
}

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}
