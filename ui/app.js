const STEPS = ["uploaded", "processing", "processed", "matching", "matched", "notified"];
const POLL_MS = 1500;

const form = document.getElementById("upload-form");
const fileInput = document.getElementById("file");
const fileLabel = document.getElementById("file-label");
const submit = document.getElementById("submit");
const statusBox = document.getElementById("status");
const counts = document.getElementById("counts");
const message = document.getElementById("message");

fileInput.addEventListener("change", () => {
  fileLabel.textContent = fileInput.files[0]?.name ?? "Choose a CSV file";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  submit.disabled = true;
  statusBox.hidden = false;
  setMessage("Requesting upload link…");
  try {
    const { upload_id, url, fields } = await requestUpload(file.name);
    setMessage("Uploading…");
    await sendToStorage(url, fields, file);
    await poll(upload_id);
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    submit.disabled = false;
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
  for (;;) {
    const response = await fetch(`/uploads/${uploadId}`);
    const upload = await response.json();
    render(upload);
    if (upload.status === "failed") throw new Error(upload.error ?? "Processing failed");
    if (upload.status === "notified") return setMessage("Done. Check the test inbox.");
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
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
