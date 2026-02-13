const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const games = {
  brick_breaker: {
    script: 'brick_breaker_game.py',
    args: ['--physical', '--camera-index', '1'],
    supportsPlayerName: true,
  },
  subway_surfers: {
    script: 'subway_surfers_game.py',
    args: ['--physical', '--camera-index', '1'],
    supportsPlayerName: true,
  },
  line: {
    script: 'line.py',
    args: ['--physical', '--camera-index', '1'],
    supportsPlayerName: true,
  },
  hole: {
    script: 'hole.py',
    args: ['--physical', '--camera-index', '1'],
    supportsPlayerName: true,
  },
};

function getScriptsDir() {
  return path.join(__dirname, '..', 'lib', 'wrappers', 'python');
}

function isExecutableFile(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function findExecutableOnPath(command) {
  const pathEnv = process.env.PATH || '';
  const pathEntries = pathEnv.split(path.delimiter).filter(Boolean);

  const extensions = process.platform === 'win32'
    ? (process.env.PATHEXT ? process.env.PATHEXT.split(';') : ['.EXE', '.CMD', '.BAT'])
    : [''];

  for (const dir of pathEntries) {
    for (const ext of extensions) {
      const candidate = path.join(dir, process.platform === 'win32' ? `${command}${ext}` : command);
      if (fs.existsSync(candidate) && isExecutableFile(candidate)) {
        return candidate;
      }
    }
  }

  return null;
}

function getPythonExecutable() {
  if (process.env.PYTHON_EXECUTABLE) {
    return process.env.PYTHON_EXECUTABLE;
  }

  const contourWallDir = path.join(__dirname, '..');
  const candidatePaths = [
    // Windows paths
    path.join(contourWallDir, '.venv', 'Scripts', 'python.exe'),
    path.join(contourWallDir, '..', '.venv', 'Scripts', 'python.exe'),
    path.join(contourWallDir, '..', '..', '.venv', 'Scripts', 'python.exe'),
    // Linux/macOS paths
    path.join(contourWallDir, '.venv', 'bin', 'python'),
    path.join(contourWallDir, '.venv', 'bin', 'python3'),
    path.join(contourWallDir, '..', '.venv', 'bin', 'python'),
    path.join(contourWallDir, '..', '.venv', 'bin', 'python3'),
    path.join(contourWallDir, '..', '..', '.venv', 'bin', 'python'),
    path.join(contourWallDir, '..', '..', '.venv', 'bin', 'python3'),
  ];

  for (const candidate of candidatePaths) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  // Fallback to system python on PATH
  if (process.platform === 'win32') {
    return findExecutableOnPath('python') || findExecutableOnPath('py') || 'python.exe';
  }

  return findExecutableOnPath('python3') || findExecutableOnPath('python') || 'python3';
}

function quoteArg(value) {
  if (!value) {
    return '""';
  }
  return `"${String(value).replace(/"/g, '\\"')}"`;
}

function getLogFilePath() {
  try {
    // Safe after app ready; launch happens via IPC after window creation.
    return path.join(app.getPath('userData'), 'launcher.log');
  } catch {
    return path.join(__dirname, 'launcher.log');
  }
}

function logLine(line) {
  try {
    fs.appendFileSync(getLogFilePath(), `${new Date().toISOString()} ${line}\n`);
  } catch {
    // ignore logging failures
  }
}

function spawnDetached(command, commandArgs, options) {
  const child = spawn(command, commandArgs, {
    detached: true,
    stdio: 'ignore',
    ...options,
  });
  child.unref();
  return child;
}

function spawnAndWaitForFailure(command, commandArgs, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, options);
    let settled = false;

    const settleOk = () => {
      if (settled) return;
      settled = true;
      resolve({ ok: true, child });
    };

    const settleFail = (message) => {
      if (settled) return;
      settled = true;
      reject(new Error(message));
    };

    child.once('error', (err) => {
      settleFail(err?.message || String(err));
    });

    // If a GUI terminal can't open (no DISPLAY, missing deps), it often exits immediately.
    const quickExitTimer = setTimeout(() => {
      settleOk();
    }, 600);

    child.once('exit', (code, signal) => {
      clearTimeout(quickExitTimer);
      if (code === 0) {
        settleOk();
        return;
      }
      const reason = signal ? `signal ${signal}` : `exit code ${code}`;
      settleFail(`${command} failed (${reason})`);
    });
  });
}

async function launchDirect(pythonExec, scriptPath, args, scriptsDir) {
  // Probe for immediate failures (ENOENT, permission, immediate nonzero exit).
  try {
    const result = await spawnAndWaitForFailure(pythonExec, [scriptPath, ...args], {
      cwd: scriptsDir,
      stdio: 'ignore',
    });
    // Detach a second time so it survives Electron exits and is consistent with Windows behavior.
    // (The probed process is already started; we keep it running.)
    try {
      result.child.unref?.();
    } catch {
      // ignore
    }
    return { ok: true, launched: 'direct' };
  } catch (err) {
    const message = String(err?.message || err);
    logLine(`Direct launch failed: python=${pythonExec} script=${scriptPath} args=${JSON.stringify(args)} err=${message}`);
    throw new Error(`Failed to start game with Python (${pythonExec}): ${message}`);
  }
}

async function launchInTerminal(gameKey, playerName) {
  const scriptsDir = getScriptsDir();
  const pythonExec = getPythonExecutable();
  const game = games[gameKey];
  const scriptPath = path.join(scriptsDir, game.script);
  const args = [...(game.args || [])];

  if (!fs.existsSync(scriptsDir)) {
    throw new Error(`Scripts directory not found: ${scriptsDir}`);
  }

  if (!fs.existsSync(scriptPath)) {
    throw new Error(`Game script not found: ${scriptPath}`);
  }

  if (game.supportsPlayerName && playerName) {
    args.push('--player-name', playerName);
  }

  if (process.platform === 'win32') {
    const pythonPath = path.normalize(pythonExec);
    const scriptFile = path.normalize(scriptPath);
    spawnDetached(pythonPath, [scriptFile, ...args], {
      cwd: scriptsDir,
      windowsHide: false,
    });
    return { ok: true, launched: 'direct' };
  }

  if (process.platform === 'darwin') {
    const shellArgs = [scriptPath, ...args].map((arg) => `'${String(arg).replace(/'/g, "'\\''")}'`).join(' ');
    const osaScript = `tell application "Terminal" to do script "${pythonExec} ${shellArgs}"`;
    spawnDetached('osascript', ['-e', osaScript], {
      cwd: scriptsDir,
    });
    return { ok: true, launched: 'terminal' };
  }

  if (process.platform === 'linux') {
    const hasGuiSession = Boolean(process.env.DISPLAY || process.env.WAYLAND_DISPLAY);
    const envTerminal = typeof process.env.TERMINAL === 'string' ? process.env.TERMINAL.trim() : '';
    const terminalCandidates = [
      envTerminal,
      'x-terminal-emulator',
      'gnome-terminal',
      'konsole',
      'xfce4-terminal',
      'xterm',
      'lxterminal',
      'mate-terminal',
    ].filter(Boolean);

    const terminalCmd = terminalCandidates
      .map((t) => ({ name: t, resolved: findExecutableOnPath(t) }))
      .find((t) => t.resolved)?.name;

    // Use bash -lc with positional args to avoid quoting issues.
    const bashLaunch = 'cd "$1" && shift && exec "$@"';
    const bashArgs = ['-lc', bashLaunch, 'bash', scriptsDir, pythonExec, scriptPath, ...args];

    if (terminalCmd && hasGuiSession) {
      let terminalArgs;
      if (terminalCmd === 'gnome-terminal' || terminalCmd === 'mate-terminal') {
        terminalArgs = ['--', 'bash', ...bashArgs];
      } else if (terminalCmd === 'xfce4-terminal') {
        terminalArgs = ['-x', 'bash', ...bashArgs];
      } else {
        // x-terminal-emulator, konsole, xterm, lxterminal
        terminalArgs = ['-e', 'bash', ...bashArgs];
      }

      try {
        await spawnAndWaitForFailure(terminalCmd, terminalArgs, {
          stdio: 'ignore',
        });
        return { ok: true, launched: 'terminal' };
      } catch (err) {
        const reason = String(err?.message || err);
        logLine(`Terminal launch failed: terminal=${terminalCmd} reason=${reason}. Falling back to direct.`);
        const direct = await launchDirect(pythonExec, scriptPath, args, scriptsDir);
        return { ...direct, message: `Terminal launch failed; ran directly. (${reason})` };
      }
    }

    // No GUI session or terminal available: still run the game.
    const direct = await launchDirect(pythonExec, scriptPath, args, scriptsDir);
    return { ...direct, message: hasGuiSession ? 'No terminal found; ran directly.' : 'No GUI session detected; ran directly.' };
  }

  // Unknown platform: run directly.
  return await launchDirect(pythonExec, scriptPath, args, scriptsDir);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 960,
    height: 720,
    minWidth: 640,
    minHeight: 480,
    resizable: true,
    maximizable: true,
    fullscreenable: true,
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  win.maximize();

  win.loadFile(path.join(__dirname, 'index.html'));
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

ipcMain.handle('launch-game', async (event, payload) => {
  const key = payload?.key;
  const playerName = typeof payload?.playerName === 'string' ? payload.playerName.trim() : '';
  const game = games[key];
  if (!game) {
    return { ok: false, message: 'Unknown game selection.' };
  }

  try {
    const result = await launchInTerminal(key, playerName);
    logLine(`Launch ok: key=${key} launched=${result?.launched || 'unknown'} msg=${result?.message || ''}`);
    return { ok: true, ...result };
  } catch (error) {
    logLine(`Launch error: key=${key} err=${String(error?.message || error)}`);
    dialog.showErrorBox('Launch failed', String(error));
    return { ok: false, message: String(error) };
  }
});


