let snowfall;

function createSnowfall() {
  const layer = document.createElement("div");
  layer.className = "snowfall";
  layer.setAttribute("aria-hidden", "true");
  const count = matchMedia("(max-width: 520px)").matches ? 24 : 48;

  for (let index = 0; index < count; index++) {
    const flake = document.createElement("span");
    const foreground = index % 4 === 0;
    const duration = 13 + Math.random() * 14;

    flake.className = foreground ? "snowfall__flake snowfall__flake--near" : "snowfall__flake";
    flake.textContent = foreground ? "❄" : "•";
    flake.style.setProperty("--x", `${(index + Math.random()) / count * 100}%`);
    flake.style.setProperty("--size", `${(foreground ? 12 : 5) + Math.random() * 10}px`);
    flake.style.setProperty("--fall-time", `${duration}s`);
    flake.style.setProperty("--delay", `${-Math.random() * duration}s`);
    flake.style.setProperty("--drift", `${Math.random() * 100 - 50}px`);
    layer.append(flake);
  }

  return layer;
}

export function toggleSnow(button) {
  if (snowfall) {
    snowfall.remove();
    snowfall = undefined;
  } else {
    snowfall = createSnowfall();
    document.body.append(snowfall);
  }

  button.setAttribute("aria-pressed", String(Boolean(snowfall)));
  button.querySelector(".snow-toggle__state").textContent = snowfall ? "Ativado" : "Desativado";
}
