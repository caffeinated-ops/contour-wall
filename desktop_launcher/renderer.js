const statusEl = document.querySelector('[data-status]');
const nameInput = document.querySelector('[data-player]');



const storedName = localStorage.getItem('playerName');
if (storedName && nameInput) {
  nameInput.value = storedName;
}

if (nameInput) {
  nameInput.addEventListener('input', () => {
    localStorage.setItem('playerName', nameInput.value.trim());
  });
}





document.querySelectorAll('[data-game]').forEach((button) => {
  button.addEventListener('click', async () => {
    const key = button.getAttribute('data-game');
    const playerName = nameInput ? nameInput.value.trim() : '';

    statusEl.textContent = 'Launching...';
    const result = await window.launcher.launchGame(key, playerName);
    if (result.ok) {
      const name = nameInput ? nameInput.value.trim() : '';
      const base = name
        ? `Launched in a new terminal window for ${name}.`
        : 'Launched in a new terminal window.';
      statusEl.textContent = result.message ? `${base} ${result.message}` : base;
    } else {
      statusEl.textContent = result.message || 'Failed to launch.';
    }
  });
});
