const statusEl = document.querySelector('[data-status]');
const nameInput = document.querySelector('[data-player]');

const apiConfig = {
  url: 'https://api.deltacraft.io/api/users',
  apiPassword: 'KaAsKrOkAnTjE123',
};

const storedName = localStorage.getItem('playerName');
if (storedName && nameInput) {
  nameInput.value = storedName;
}

if (nameInput) {
  nameInput.addEventListener('input', () => {
    localStorage.setItem('playerName', nameInput.value.trim());
  });
}

async function capturePhoto() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('Camera access is not available.');
  }

  const devices = await navigator.mediaDevices.enumerateDevices();
  const videoInputs = devices.filter((device) => device.kind === 'videoinput');
  const preferredDevice = videoInputs[1] || videoInputs[0];

  let stream;
  const video = document.createElement('video');
  const canvas = document.createElement('canvas');
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: 640,
        height: 480,
        deviceId: preferredDevice ? { exact: preferredDevice.deviceId } : undefined,
      },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();

    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Camera did not respond.'));
      }, 5000);
      video.addEventListener(
        'loadeddata',
        () => {
          clearTimeout(timeout);
          resolve();
        },
        { once: true },
      );
    });

    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      throw new Error('Failed to capture camera frame.');
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.88));
    if (!blob) {
      throw new Error('Failed to encode camera image.');
    }
    return blob;
  } finally {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
  }
}

async function registerUser(playerName) {
  const imageBlob = await capturePhoto();
  const formData = new FormData();
  formData.append('image', imageBlob, 'player.jpg');

  const response = await fetch(apiConfig.url, {
    method: 'POST',
    headers: {
      apiPassword: apiConfig.apiPassword,
      userName: playerName,
    },
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`API request failed (${response.status}).`);
  }

  return response.json();
}

document.querySelectorAll('[data-game]').forEach((button) => {
  button.addEventListener('click', async () => {
    const key = button.getAttribute('data-game');
    const playerName = nameInput ? nameInput.value.trim() : '';
    let registrationError = null;

    if (playerName) {
      statusEl.textContent = 'Capturing photo...';
      try {
        await registerUser(playerName);
      } catch (error) {
        registrationError = error;
      }
    }

    statusEl.textContent = 'Launching...';
    const result = await window.launcher.launchGame(key, playerName);
    if (result.ok) {
      const name = nameInput ? nameInput.value.trim() : '';
      if (registrationError) {
        statusEl.textContent = `Launched for ${name}. Photo upload failed.`;
      } else {
        statusEl.textContent = name
          ? `Launched in a new terminal window for ${name}.`
          : 'Launched in a new terminal window.';
      }
    } else {
      statusEl.textContent = result.message || 'Failed to launch.';
    }
  });
});
