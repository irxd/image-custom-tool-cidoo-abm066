/**
 * Frontend Application Logic for CIDOO ABM066 Keyboard LCD Tool.
 * Handles client-side GIF decoding, frame resizing/fitting, RGB565 conversion,
 * live preview playback, and REST API communication with the backend.
 */

// State
let rawFileBuffer = null;
let currentFileType = null;
let sourceImage = null; // for static images
let gifReader = null;   // for GIFs
let decodedFrames = []; // Array of { canvas: HTMLCanvasElement, rgb565: Uint8Array, delayMs: number }
let currentFrameIndex = 0;
let isPlaying = false;
let playTimer = null;
let animationSpeedMs = 40;
let currentFitMode = 'cover';
let isDeviceConnected = false;
let isUploading = false;
let progressPollInterval = null;

// DOM Elements
const screenCanvas = document.getElementById('screenCanvas');
const screenCtx = screenCanvas.getContext('2d');
const screenBezel = document.getElementById('screenBezel');
const screenEmptyPrompt = document.getElementById('screenEmptyPrompt');
const scale1x = document.getElementById('scale1x');
const scale2x = document.getElementById('scale2x');

const statusBadge = document.getElementById('deviceStatusBadge');
const statusText = document.getElementById('statusText');
const btnSyncTime = document.getElementById('btnSyncTime');

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileLoadedInfo = document.getElementById('fileLoadedInfo');
const loadedFileName = document.getElementById('loadedFileName');
const loadedFileMeta = document.getElementById('loadedFileMeta');

const playbackControls = document.getElementById('playbackControls');
const frameScrubber = document.getElementById('frameScrubber');
const frameCounter = document.getElementById('frameCounter');
const btnPrevFrame = document.getElementById('btnPrevFrame');
const btnPlayPause = document.getElementById('btnPlayPause');
const btnNextFrame = document.getElementById('btnNextFrame');
const iconPlay = document.getElementById('iconPlay');
const iconPause = document.getElementById('iconPause');
const speedSlider = document.getElementById('speedSlider');
const speedValue = document.getElementById('speedValue');
const speedPresets = document.querySelectorAll('.preset-btn');

const fitButtons = document.querySelectorAll('#fitModeControl .segment-btn');
const slotSelect = document.getElementById('slotSelect');
const maxFramesInput = document.getElementById('maxFramesInput');
const btnUpload = document.getElementById('btnUpload');
const uploadBtnText = document.getElementById('uploadBtnText');
const progressBox = document.getElementById('progressBox');
const progressBar = document.getElementById('progressBar');
const progressMessage = document.getElementById('progressMessage');
const progressPercent = document.getElementById('progressPercent');
const toastEl = document.getElementById('toast');


// --- Toast Notification Helper ---
let toastTimeout = null;
function showToast(message, type = 'info', duration = 3500) {
  if (toastTimeout) clearTimeout(toastTimeout);
  toastEl.textContent = message;
  toastEl.className = `toast ${type}`;
  toastEl.classList.remove('hidden');
  toastTimeout = setTimeout(() => {
    toastEl.classList.add('hidden');
  }, duration);
}


// --- Status Polling ---
async function checkDeviceStatus() {
  if (isUploading) return;
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    if (data.connected) {
      isDeviceConnected = true;
      statusBadge.className = 'status-badge connected';
      const slotStr = data.slot ? `Slot ${data.slot}` : '';
      const framesStr = data.frames ? `${data.frames} frames` : '';
      const meta = [slotStr, framesStr].filter(Boolean).join(' • ');
      statusText.textContent = `Connected (${meta || 'CIDOO ABM066'})`;
      btnSyncTime.disabled = false;
    } else {
      isDeviceConnected = false;
      statusBadge.className = 'status-badge disconnected';
      statusText.textContent = 'Keyboard Disconnected';
      btnSyncTime.disabled = true;
    }
  } catch (err) {
    isDeviceConnected = false;
    statusBadge.className = 'status-badge disconnected';
    statusText.textContent = 'Server Offline';
    btnSyncTime.disabled = true;
  }
  updateUploadButtonState();
}

setInterval(checkDeviceStatus, 3500);
checkDeviceStatus();


// --- Sync Time ---
btnSyncTime.addEventListener('click', async () => {
  try {
    btnSyncTime.disabled = true;
    const slot = parseInt(slotSelect.value) || 1;
    const res = await fetch('/api/sync-time', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Clock synced to Mac: ${data.synced_time}`, 'success');
      checkDeviceStatus();
    } else {
      showToast(`Sync failed: ${data.error || 'Unknown error'}`, 'error');
    }
  } catch (err) {
    showToast(`Sync failed: ${err.message}`, 'error');
  } finally {
    btnSyncTime.disabled = false;
  }
});


// --- Scale 1x / 2x Toggle ---
scale1x.addEventListener('click', () => {
  scale1x.classList.add('active');
  scale2x.classList.remove('active');
  screenBezel.classList.remove('scale-2x');
});
scale2x.addEventListener('click', () => {
  scale2x.classList.add('active');
  scale1x.classList.remove('active');
  screenBezel.classList.add('scale-2x');
});


// --- Drag & Drop / File Input ---
dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    handleFile(e.dataTransfer.files[0]);
  }
});

fileInput.addEventListener('change', (e) => {
  if (e.target.files && e.target.files.length > 0) {
    handleFile(e.target.files[0]);
  }
});

async function handleFile(file) {
  stopPlayback();
  const ext = file.name.split('.').pop().toLowerCase();
  currentFileType = ext;
  loadedFileName.textContent = file.name;
  fileLoadedInfo.classList.remove('hidden');

  const arrayBuffer = await file.arrayBuffer();
  rawFileBuffer = arrayBuffer;

  if (ext === 'gif') {
    await processGif(arrayBuffer);
  } else {
    await processStaticImage(file);
  }

  screenEmptyPrompt.classList.add('hidden');
  updateUploadButtonState();
}


// --- Fit Calculation ---
function drawFitted(ctx, source, srcW, srcH, fit) {
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, 240, 135);

  if (fit === 'stretch') {
    ctx.drawImage(source, 0, 0, srcW, srcH, 0, 0, 240, 135);
    return;
  }

  const scaleW = 240 / srcW;
  const scaleH = 135 / srcH;
  let scale;

  if (fit === 'cover') {
    scale = Math.max(scaleW, scaleH);
  } else { // contain
    scale = Math.min(scaleW, scaleH);
  }

  const destW = srcW * scale;
  const destH = srcH * scale;
  const destX = (240 - destW) / 2;
  const destY = (135 - destH) / 2;

  ctx.drawImage(source, 0, 0, srcW, srcH, destX, destY, destW, destH);
}


// --- RGB565 Conversion Helper ---
function canvasToRgb565(ctx) {
  const imgData = ctx.getImageData(0, 0, 240, 135).data;
  const out = new Uint8Array(240 * 135 * 2);
  let src = 0;
  let dst = 0;
  for (let i = 0; i < 240 * 135; i++) {
    const r = imgData[src];
    const g = imgData[src + 1];
    const b = imgData[src + 2];
    // Big Endian 16-bit RGB565: RRRRRGGG GGGBBBBB
    const val = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
    out[dst] = (val >> 8) & 0xFF;
    out[dst + 1] = val & 0xFF;
    src += 4;
    dst += 2;
  }
  return out;
}


// --- Static Image Processing ---
async function processStaticImage(fileOrBlob) {
  playbackControls.classList.add('hidden');
  const url = URL.createObjectURL(fileOrBlob);
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = reject;
    img.src = url;
  });

  sourceImage = img;
  renderStaticFrame();
  loadedFileMeta.textContent = `Static • ${img.naturalWidth}×${img.naturalHeight}px`;
}

function renderStaticFrame() {
  if (!sourceImage) return;
  drawFitted(screenCtx, sourceImage, sourceImage.naturalWidth, sourceImage.naturalHeight, currentFitMode);
  const rgb565 = canvasToRgb565(screenCtx);
  decodedFrames = [{
    canvas: null,
    rgb565: rgb565,
    delayMs: 40
  }];
  currentFrameIndex = 0;
}


// --- GIF Processing ---
async function processGif(buffer) {
  const uint8 = new Uint8Array(buffer);
  gifReader = new GifReader(uint8);
  const totalFrames = gifReader.numFrames();
  const width = gifReader.width;
  const height = gifReader.height;

  let maxFrames = parseInt(maxFramesInput.value) || 0;
  let framesToLoad = totalFrames;
  if (maxFrames > 0 && maxFrames < totalFrames) {
    framesToLoad = maxFrames;
  }

  decodedFrames = [];
  let totalDelayMs = 0;

  // Offscreen canvas for compositing GIF frames
  const offscreen = document.createElement('canvas');
  offscreen.width = width;
  offscreen.height = height;
  const offCtx = offscreen.getContext('2d', { willReadFrequently: true });

  const targetCanvas = document.createElement('canvas');
  targetCanvas.width = 240;
  targetCanvas.height = 135;
  const targetCtx = targetCanvas.getContext('2d', { willReadFrequently: true });

  const pixelBuf = new Uint8ClampedArray(width * height * 4);
  let prevFrameInfo = null;
  let backupCanvas = null;

  for (let i = 0; i < framesToLoad; i++) {
    const frameInfo = gifReader.frameInfo(i);
    const delay = (frameInfo.delay > 0 ? frameInfo.delay : 4) * 10; // in ms
    totalDelayMs += delay;

    // Handle disposal from previous frame
    if (prevFrameInfo) {
      if (prevFrameInfo.disposal === 2) {
        // Restore to background
        offCtx.clearRect(prevFrameInfo.x, prevFrameInfo.y, prevFrameInfo.width, prevFrameInfo.height);
      } else if (prevFrameInfo.disposal === 3 && backupCanvas) {
        // Restore previous
        offCtx.drawImage(backupCanvas, 0, 0);
      }
    }

    if (frameInfo.disposal === 3) {
      if (!backupCanvas) {
        backupCanvas = document.createElement('canvas');
        backupCanvas.width = width;
        backupCanvas.height = height;
      }
      const bCtx = backupCanvas.getContext('2d');
      bCtx.clearRect(0, 0, width, height);
      bCtx.drawImage(offscreen, 0, 0);
    }

    // Decode frame pixels
    gifReader.decodeAndBlitFrameRGBA(i, pixelBuf);
    const frameImageData = new ImageData(pixelBuf, width, height);
    offCtx.putImageData(frameImageData, 0, 0);

    // Render onto 240x135 with fit
    drawFitted(targetCtx, offscreen, width, height, currentFitMode);
    const rgb565 = canvasToRgb565(targetCtx);

    // Save frame snapshot canvas for quick preview scrubbing
    const frameSnap = document.createElement('canvas');
    frameSnap.width = 240;
    frameSnap.height = 135;
    frameSnap.getContext('2d').drawImage(targetCanvas, 0, 0);

    decodedFrames.push({
      canvas: frameSnap,
      rgb565: rgb565,
      delayMs: delay
    });

    prevFrameInfo = frameInfo;
  }

  // Update speed slider from average GIF delay
  if (framesToLoad > 0) {
    const avgDelay = Math.round(totalDelayMs / framesToLoad);
    animationSpeedMs = Math.max(20, Math.min(200, avgDelay));
    speedSlider.value = animationSpeedMs;
    speedValue.textContent = animationSpeedMs;
    updateSpeedPresetButtons(animationSpeedMs);
  }

  // Update Scrubber
  frameScrubber.min = 0;
  frameScrubber.max = decodedFrames.length - 1;
  frameScrubber.value = 0;
  currentFrameIndex = 0;

  displayFrame(0);
  playbackControls.classList.remove('hidden');
  loadedFileMeta.textContent = `${decodedFrames.length} frames (${totalFrames} total) • ${width}×${height}px`;

  startPlayback();
}

function recomputeFramesForFit() {
  if (!rawFileBuffer) return;
  if (currentFileType === 'gif') {
    processGif(rawFileBuffer);
  } else if (sourceImage) {
    renderStaticFrame();
    displayFrame(0);
  }
}


// --- Fit Mode Buttons ---
fitButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    fitButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFitMode = btn.dataset.fit;
    recomputeFramesForFit();
  });
});

maxFramesInput.addEventListener('change', () => {
  if (currentFileType === 'gif' && rawFileBuffer) {
    processGif(rawFileBuffer);
  }
});


// --- Playback Controller ---
function displayFrame(index) {
  if (!decodedFrames || decodedFrames.length === 0) return;
  currentFrameIndex = Math.max(0, Math.min(decodedFrames.length - 1, index));
  const frame = decodedFrames[currentFrameIndex];
  if (frame.canvas) {
    screenCtx.drawImage(frame.canvas, 0, 0);
  }
  frameScrubber.value = currentFrameIndex;
  frameCounter.textContent = `Frame ${currentFrameIndex + 1} / ${decodedFrames.length}`;
}

function startPlayback() {
  if (isPlaying || decodedFrames.length <= 1) return;
  isPlaying = true;
  iconPlay.classList.add('hidden');
  iconPause.classList.remove('hidden');
  scheduleNextFrame();
}

function stopPlayback() {
  isPlaying = false;
  if (playTimer) {
    clearTimeout(playTimer);
    playTimer = null;
  }
  iconPlay.classList.remove('hidden');
  iconPause.classList.add('hidden');
}

function scheduleNextFrame() {
  if (!isPlaying) return;
  playTimer = setTimeout(() => {
    currentFrameIndex = (currentFrameIndex + 1) % decodedFrames.length;
    displayFrame(currentFrameIndex);
    scheduleNextFrame();
  }, animationSpeedMs);
}

btnPlayPause.addEventListener('click', () => {
  if (isPlaying) {
    stopPlayback();
  } else {
    startPlayback();
  }
});

btnPrevFrame.addEventListener('click', () => {
  stopPlayback();
  let idx = currentFrameIndex - 1;
  if (idx < 0) idx = decodedFrames.length - 1;
  displayFrame(idx);
});

btnNextFrame.addEventListener('click', () => {
  stopPlayback();
  let idx = (currentFrameIndex + 1) % decodedFrames.length;
  displayFrame(idx);
});

frameScrubber.addEventListener('input', (e) => {
  stopPlayback();
  displayFrame(parseInt(e.target.value));
});


// --- Speed Controls ---
speedSlider.addEventListener('input', (e) => {
  animationSpeedMs = parseInt(e.target.value);
  speedValue.textContent = animationSpeedMs;
  updateSpeedPresetButtons(animationSpeedMs);
});

function updateSpeedPresetButtons(speed) {
  speedPresets.forEach(btn => {
    if (parseInt(btn.dataset.speed) === speed) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

speedPresets.forEach(btn => {
  btn.addEventListener('click', () => {
    animationSpeedMs = parseInt(btn.dataset.speed);
    speedSlider.value = animationSpeedMs;
    speedValue.textContent = animationSpeedMs;
    updateSpeedPresetButtons(animationSpeedMs);
  });
});


// --- Upload Button State ---
function updateUploadButtonState() {
  const hasFrames = decodedFrames && decodedFrames.length > 0;
  btnUpload.disabled = !hasFrames || isUploading || !isDeviceConnected;
  if (!isDeviceConnected) {
    uploadBtnText.textContent = 'Connect Keyboard via USB';
  } else if (!hasFrames) {
    uploadBtnText.textContent = 'Select or Drop an Image';
  } else if (isUploading) {
    uploadBtnText.textContent = 'Uploading to Keyboard...';
  } else {
    uploadBtnText.textContent = `Upload to LCD (Slot ${slotSelect.value})`;
  }
}

slotSelect.addEventListener('change', updateUploadButtonState);


// --- Upload Execution ---
btnUpload.addEventListener('click', async () => {
  if (!decodedFrames || decodedFrames.length === 0 || isUploading) return;

  isUploading = true;
  updateUploadButtonState();
  progressBox.classList.remove('hidden');
  progressBar.style.width = '0%';
  progressPercent.textContent = '0%';
  progressMessage.textContent = 'Preparing upload...';

  const slot = parseInt(slotSelect.value) || 1;
  const interval = animationSpeedMs;
  const frameCount = decodedFrames.length;

  // Combine raw RGB565 frames into one binary Uint8Array
  const frameSize = 240 * 135 * 2; // 64,800
  const combined = new Uint8Array(frameCount * frameSize);
  for (let i = 0; i < frameCount; i++) {
    combined.set(decodedFrames[i].rgb565, i * frameSize);
  }

  try {
    // Initiate background upload on server
    const res = await fetch('/api/upload', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-Slot': slot.toString(),
        'X-Interval': interval.toString(),
        'X-Frame-Count': frameCount.toString()
      },
      body: combined
    });

    const initData = await res.json();
    if (!res.ok || !initData.success) {
      throw new Error(initData.error || 'Failed to start upload');
    }

    // Poll upload progress
    progressPollInterval = setInterval(async () => {
      try {
        const pRes = await fetch('/api/progress');
        const pData = await pRes.json();

        progressBar.style.width = `${pData.percent}%`;
        progressPercent.textContent = `${pData.percent}%`;
        progressMessage.textContent = pData.message;

        if (pData.error) {
          clearInterval(progressPollInterval);
          isUploading = false;
          updateUploadButtonState();
          showToast(`Upload failed: ${pData.error}`, 'error', 6000);
          return;
        }

        if (!pData.busy && pData.last_result && pData.last_result.success) {
          clearInterval(progressPollInterval);
          progressBar.style.width = '100%';
          progressPercent.textContent = '100%';
          progressMessage.textContent = 'Upload Complete!';
          isUploading = false;
          updateUploadButtonState();
          showToast('Image uploaded successfully to CIDOO ABM066 LCD!', 'success', 5000);
          checkDeviceStatus();
          setTimeout(() => {
            if (!isUploading) progressBox.classList.add('hidden');
          }, 3500);
        }
      } catch (pollErr) {
        console.error('Progress poll error:', pollErr);
      }
    }, 250);

  } catch (err) {
    isUploading = false;
    updateUploadButtonState();
    showToast(`Error: ${err.message}`, 'error', 6000);
    progressBox.classList.add('hidden');
  }
});
