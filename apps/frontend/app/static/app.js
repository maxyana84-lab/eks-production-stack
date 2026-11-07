const api = window.APP_CONFIG.apiUrl;
const list = document.getElementById("items");
const status = document.getElementById("status");

async function load() {
  try {
    const response = await fetch(`${api}/api/items`);
    const { items } = await response.json();
    list.replaceChildren(...items.map(i => Object.assign(document.createElement("li"), { textContent: i.name })));
    status.textContent = "";
  } catch (e) {
    status.textContent = "backend is not reachable";
  }
}

document.getElementById("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.getElementById("name");
  await fetch(`${api}/api/items`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: input.value }) });
  input.value = "";
  load();
});

load();
