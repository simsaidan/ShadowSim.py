function click(node) {
  const view = node.ownerDocument.defaultView;
  node.dispatchEvent(new view.MouseEvent("click", { bubbles: false }));
}

function typeInto(node, value) {
  node.value = value;
  node.dispatchEvent(new node.ownerDocument.defaultView.Event("input"));
}

function insertAt(node, index, text) {
  const value = String(node.value ?? "");
  const next = value.slice(0, index) + text + value.slice(index);
  const caret = index + text.length;
  node.focus();
  node.value = next;
  node.setSelectionRange(caret, caret);
  node.dispatchEvent(new node.ownerDocument.defaultView.Event("input"));
}

function setChange(node, value) {
  if (value != null) node.value = value;
  node.dispatchEvent(new node.ownerDocument.defaultView.Event("change"));
}

function setChecked(node, checked) {
  node.checked = checked;
  node.dispatchEvent(new node.ownerDocument.defaultView.Event("change"));
}

function installDownloads(window) {
  const downloads = [];
  window.URL.createObjectURL = (blob) => {
    downloads.push({ blob, type: blob.type });
    return "blob:board";
  };
  window.URL.revokeObjectURL = () => {};
  window.HTMLAnchorElement.prototype.click = function () {
    downloads.push({
      name: this.getAttribute("download") || "",
      href: this.getAttribute("href") || "",
    });
  };
  return downloads;
}

async function settle() {
  for (let step = 0; step < 8; step += 1) await Promise.resolve();
}

module.exports = { click, insertAt, installDownloads, setChange, setChecked, settle, typeInto };
