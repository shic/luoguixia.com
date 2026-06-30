(() => {
  const recipient = "luoguixia@gmail.com";

  function labelFor(name) {
    return name.replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
  }

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches(".fusion-form")) {
      return;
    }

    event.preventDefault();
    const data = new FormData(form);
    const lines = [];

    for (const [name, value] of data.entries()) {
      if (typeof value !== "string" || !value.trim()) {
        continue;
      }
      if (name.startsWith("fusion_") || name.startsWith("privacy_")) {
        continue;
      }
      lines.push(`${labelFor(name)}: ${value.trim()}`);
    }

    const subject = data.get("subject") || "Website contact";
    const body = lines.join("\n");
    window.location.href = `mailto:${recipient}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  });
})();
