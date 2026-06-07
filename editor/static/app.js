const state = {
  currentSlug: "",
  dirty: false,
};

const $ = (selector) => document.querySelector(selector);

const fields = {
  title: $("#title"),
  slug: $("#slug"),
  date: $("#date"),
  tags: $("#tags"),
  description: $("#description"),
  featureImage: $("#featureImage"),
  editor: $("#editor"),
  postList: $("#postList"),
  status: $("#status"),
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

function slugify(value) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function setStatus(message, tone = "neutral") {
  fields.status.textContent = message;
  fields.status.dataset.tone = tone;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || data.output || "请求失败");
  }
  return data;
}

function markDirty() {
  state.dirty = true;
  setStatus("有未保存改动");
}

function metaFromForm() {
  return {
    title: fields.title.value.trim(),
    date: fields.date.value,
    tags: fields.tags.value.trim(),
    description: fields.description.value.trim(),
    feature_image: fields.featureImage.value.trim(),
  };
}

function fillForm(post) {
  const meta = post.meta || {};
  state.currentSlug = post.slug || "";
  fields.title.value = meta.title || "";
  fields.slug.value = post.slug || "";
  fields.date.value = meta.date || today();
  fields.tags.value = meta.tags || "";
  fields.description.value = meta.description || "";
  fields.featureImage.value = meta.feature_image || "";
  fields.editor.innerHTML = post.html || "<p></p>";
  state.dirty = false;
  setStatus(state.currentSlug ? `已打开：${state.currentSlug}.md` : "新文章");
}

async function loadPosts() {
  const data = await api("/api/posts");
  fields.postList.innerHTML = "";
  data.posts.forEach((post) => {
    const button = document.createElement("button");
    button.className = "post-item";
    button.dataset.slug = post.slug;
    button.innerHTML = `<strong>${escapeHtml(post.title)}</strong><span>${escapeHtml(post.date || "无日期")} · ${escapeHtml(post.tags || "无标签")}</span>`;
    button.addEventListener("click", () => openPost(post.slug));
    fields.postList.appendChild(button);
  });
  updateActivePost();
}

function updateActivePost() {
  document.querySelectorAll(".post-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.slug === state.currentSlug);
  });
}

async function openPost(slug) {
  if (state.dirty && !confirm("当前文章还没保存，要继续打开其他文章吗？")) {
    return;
  }
  const post = await api(`/api/post?slug=${encodeURIComponent(slug)}`);
  fillForm(post);
  updateActivePost();
}

function newPost() {
  if (state.dirty && !confirm("当前文章还没保存，要新建文章吗？")) {
    return;
  }
  fillForm({
    slug: "",
    meta: {
      title: "",
      date: today(),
      tags: "",
      description: "",
      feature_image: "",
    },
    html: "<p>开始写文章。</p>",
  });
  fields.title.focus();
  updateActivePost();
}

async function savePost() {
  const meta = metaFromForm();
  if (!meta.title) {
    alert("先写标题。");
    fields.title.focus();
    return;
  }
  const slug = fields.slug.value.trim() || slugify(meta.title);
  const result = await api("/api/post", {
    method: "POST",
    body: JSON.stringify({
      oldSlug: state.currentSlug,
      slug,
      meta,
      html: fields.editor.innerHTML,
    }),
  });
  state.currentSlug = result.slug;
  fields.slug.value = result.slug;
  state.dirty = false;
  setStatus(`已保存：${result.slug}.md`);
  await loadPosts();
}

async function buildSite() {
  await savePost();
  setStatus("正在生成静态页面...");
  const result = await api("/api/build", { method: "POST", body: "{}" });
  setStatus(result.output.trim().split("\n").slice(-1)[0] || "生成完成");
}

async function publishSite() {
  await savePost();
  if (!confirm("确定要生成、提交并推送到 GitHub Pages 吗？")) {
    return;
  }
  setStatus("正在发布到 GitHub Pages...");
  const result = await api("/api/publish", { method: "POST", body: "{}" });
  const tail = result.output.trim().split("\n").filter(Boolean).slice(-3).join(" · ");
  setStatus(tail || "发布完成");
}

function execCommand(command, value = null) {
  fields.editor.focus();
  document.execCommand(command, false, value);
  markDirty();
}

function createLink() {
  const url = prompt("链接地址");
  if (!url) return;
  execCommand("createLink", url);
}

function insertNode(node) {
  fields.editor.focus();
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) {
    fields.editor.appendChild(node);
    return;
  }
  const range = selection.getRangeAt(0);
  range.deleteContents();
  range.insertNode(node);
  range.setStartAfter(node);
  range.collapse(true);
  selection.removeAllRanges();
  selection.addRange(range);
}

function insertCodeBlock() {
  const pre = document.createElement("pre");
  const code = document.createElement("code");
  code.textContent = "在这里写代码";
  pre.appendChild(code);
  insertNode(pre);
  markDirty();
}

function insertTable() {
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const tbody = document.createElement("tbody");
  const headerRow = document.createElement("tr");
  ["参数", "说明", "备注"].forEach((text) => {
    const th = document.createElement("th");
    th.textContent = text;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  for (let rowIndex = 0; rowIndex < 2; rowIndex += 1) {
    const row = document.createElement("tr");
    for (let columnIndex = 0; columnIndex < 3; columnIndex += 1) {
      const td = document.createElement("td");
      td.textContent = "";
      row.appendChild(td);
    }
    tbody.appendChild(row);
  }
  table.appendChild(thead);
  table.appendChild(tbody);
  insertNode(table);
  markDirty();
}

function fileToDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function uploadImage(file) {
  setStatus("正在保存图片...");
  const data = await fileToDataURL(file);
  const result = await api("/api/image", {
    method: "POST",
    body: JSON.stringify({ name: file.name, data }),
  });
  insertImage(result.src, result.markdownSrc, file.name);
  markDirty();
  setStatus("图片已插入，记得保存文章");
}

function insertImage(src, markdownSrc, alt = "") {
  fields.editor.focus();
  const img = document.createElement("img");
  img.src = src;
  img.alt = alt;
  img.dataset.mdSrc = markdownSrc;
  insertNode(img);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.querySelectorAll("[data-command]").forEach((button) => {
  button.addEventListener("click", () => execCommand(button.dataset.command, button.dataset.value || null));
});

$("#linkButton").addEventListener("click", createLink);
$("#codeButton").addEventListener("click", insertCodeBlock);
$("#tableButton").addEventListener("click", insertTable);
$("#newPost").addEventListener("click", newPost);
$("#saveButton").addEventListener("click", () => savePost().catch((error) => setStatus(error.message, "error")));
$("#buildButton").addEventListener("click", () => buildSite().catch((error) => setStatus(error.message, "error")));
$("#publishButton").addEventListener("click", () => publishSite().catch((error) => setStatus(error.message, "error")));

$("#imageButton").addEventListener("click", () => $("#imageInput").click());
$("#imageInput").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) uploadImage(file).catch((error) => setStatus(error.message, "error"));
  event.target.value = "";
});

fields.editor.addEventListener("paste", (event) => {
  const files = [...event.clipboardData.files].filter((file) => file.type.startsWith("image/"));
  if (!files.length) return;
  event.preventDefault();
  files.forEach((file) => uploadImage(file).catch((error) => setStatus(error.message, "error")));
});

fields.editor.addEventListener("input", markDirty);
Object.values(fields).forEach((field) => {
  if (field instanceof HTMLInputElement) {
    field.addEventListener("input", markDirty);
  }
});

fields.title.addEventListener("input", () => {
  if (!state.currentSlug && !fields.slug.value.trim()) {
    fields.slug.value = slugify(fields.title.value);
  }
});

window.addEventListener("beforeunload", (event) => {
  if (!state.dirty) return;
  event.preventDefault();
  event.returnValue = "";
});

loadPosts()
  .then(() => {
    const first = document.querySelector(".post-item");
    if (first) {
      return openPost(first.dataset.slug);
    }
    newPost();
  })
  .catch((error) => setStatus(error.message, "error"));
