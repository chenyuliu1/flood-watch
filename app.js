// 90051 sensor chart + flask storage
var BAUD_RATE = 9600;
var MAX_POINTS = 30;

var THRESHOLD_WARNING = 1.5;   // metres — minor flood
var THRESHOLD_DANGER = 3.0;    // metres — major flood

var FLASK_URL = "http://localhost:5001";

var POLL_INTERVAL = 5000;

var sensorChart = null;
var chartCanvas = null;

var chartLabels = [];
var chartValues = [];
var sampleSeq = 0;
var totalSamples = 0;
var invalidLines = 0;

var keepReading = false;
var portRef = null;
var readerRef = null;
var readableClosedRef = null;

var elConnStatus = null;
var elLatest = null;
var elSampleCount = null;
var elInvalidCount = null;
var elErrorLine = null;
var elUnsupported = null;
var btnConnect = null;
var btnDisconnect = null;
var btnClear = null;

var elRiskLevel = null;
var elRiskReasons = null;
var elFlaskStatus = null;

var serialSupported = false;

document.addEventListener("DOMContentLoaded", function () {
  chartCanvas = document.getElementById("sensorChart");
  elConnStatus = document.getElementById("serialConnStatus");
  elLatest = document.getElementById("serialLatestValue");
  elSampleCount = document.getElementById("serialSampleCount");
  elInvalidCount = document.getElementById("serialInvalidCount");
  elErrorLine = document.getElementById("serialErrorLine");
  elUnsupported = document.getElementById("serialUnsupported");
  btnConnect = document.getElementById("btnSerialConnect");
  btnDisconnect = document.getElementById("btnSerialDisconnect");
  btnClear = document.getElementById("btnSerialClear");

  
  elRiskLevel = document.getElementById("riskLevel");
  elRiskReasons = document.getElementById("riskReasons");
  elFlaskStatus = document.getElementById("flaskStatus");

  if (!chartCanvas || !elConnStatus || !btnConnect || !btnDisconnect || !btnClear) {
    return;
  }

  initChart();

  serialSupported = typeof navigator !== "undefined" && "serial" in navigator;
  if (!serialSupported && elUnsupported) {
    elUnsupported.classList.remove("hidden");
  }
  if (!serialSupported) {
    btnConnect.disabled = true;
    setConnStatus("Unavailable");
  }

  btnConnect.addEventListener("click", function () {
    connectToArduino().catch(function (err) {
      showError("Unexpected error: " + (err && err.message ? err.message : String(err)));
    });
  });
  btnDisconnect.addEventListener("click", function () {
    disconnectSerial().catch(function () { });
  });
  btnClear.addEventListener("click", function () {
    clearChartData();
  });

  if (serialSupported && navigator.serial && navigator.serial.addEventListener) {
    navigator.serial.addEventListener("disconnect", function (event) {
      if (portRef && event.target === portRef) {
        showError("Serial port disconnected.");
        disconnectSerial();
      }
    });
  }

  
  fetchRiskLevel();
  setInterval(fetchRiskLevel, POLL_INTERVAL);

  
  var btnSimulate = document.getElementById("btnSimulate");
  var btnSimStop = document.getElementById("btnSimStop");
  if (btnSimulate) {
    btnSimulate.addEventListener("click", function () { startSimulation(); });
  }
  if (btnSimStop) {
    btnSimStop.addEventListener("click", function () { stopSimulation(); });
  }
});

var readingBuffer = [];
var SAVE_INTERVAL = 5000;

setInterval(flushBufferToFlask, SAVE_INTERVAL);

function bufferReading(value, label, extras) {
  readingBuffer.push({ value: value, label: label || "water_level", extras: extras || {} });
}

function flushBufferToFlask() {
  if (readingBuffer.length === 0) return;

  var sum = 0;
  var rateSum = 0;
  var hasRate = false;
  var label = readingBuffer[0].label;
  for (var i = 0; i < readingBuffer.length; i++) {
    sum += readingBuffer[i].value;
    if (readingBuffer[i].extras && readingBuffer[i].extras.rate_m_min !== undefined) {
      rateSum += readingBuffer[i].extras.rate_m_min;
      hasRate = true;
    }
  }
  var avg = Math.round((sum / readingBuffer.length) * 100) / 100;
  var avgRate = hasRate ? Math.round((rateSum / readingBuffer.length) * 100) / 100 : null;
  var count = readingBuffer.length;
  var latest = readingBuffer[readingBuffer.length - 1];

  readingBuffer = [];

  var payload = {};
  payload[label] = avg;
  payload["samples_averaged"] = count;
  if (avgRate !== null) payload["rate_m_min"] = avgRate;
  if (latest.extras) {
    if (latest.extras.raw_distance !== undefined) payload["raw_distance"] = latest.extras.raw_distance;
    if (latest.extras.level_original !== undefined) payload["level_original"] = latest.extras.level_original;
    if (latest.extras.rate_original !== undefined) payload["rate_original"] = latest.extras.rate_original;
    if (latest.extras.state) payload["arduino_state"] = latest.extras.state;
    if (latest.extras.button !== undefined) payload["button"] = latest.extras.button;
    if (latest.extras.acknowledged !== undefined) payload["acknowledged"] = latest.extras.acknowledged;
    if (latest.extras.yellow_led !== undefined) payload["yellow_led"] = latest.extras.yellow_led;
    if (latest.extras.red_led !== undefined) payload["red_led"] = latest.extras.red_led;
    if (latest.extras.buzzer !== undefined) payload["buzzer"] = latest.extras.buzzer;
  }

  fetch(FLASK_URL + "/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then(function (res) { return res.json(); })
    .then(function (data) {
      if (elFlaskStatus) {
        elFlaskStatus.textContent = "Saved avg of " + count + " readings: " + avg + " (" + data.timestamp + ")";
      }
    })
    .catch(function (err) {
      if (elFlaskStatus) {
        elFlaskStatus.textContent = "Flask offline - data not saved";
      }
    });
}

function fetchRiskLevel() {
  fetch(FLASK_URL + "/risk")
    .then(function (res) { return res.json(); })
    .then(function (data) {
      if (elRiskLevel) {
        elRiskLevel.textContent = data.level;
        elRiskLevel.className = "";
        if (data.level === "DANGER") elRiskLevel.className = "status-danger";
        else if (data.level === "WARNING") elRiskLevel.className = "status-warning";
        else elRiskLevel.className = "status-normal";
      }
      if (elRiskReasons) {
        elRiskReasons.textContent = data.reasons.join("; ");
      }
      // update display
      var elWater = document.getElementById("currentWaterLevel");
      if (elWater && data.factors) {
        elWater.textContent = data.factors.water_level_m.toFixed(2) + " m";
      }
      var elRainfall = document.getElementById("currentRainfall");
      if (elRainfall && data.factors) {
        elRainfall.textContent = data.factors.rainfall_24h_mm.toFixed(1) + " mm";
      }
    })
    .catch(function () {
      
    });
}

// mm to display scale (15mm -> 1.5m warning, 30mm -> 3.0m danger)
var LEVEL_UNIT_TO_METRES = 0.1;

function parseSerialLine(line) {
  line = line.trim();
  if (!line) return null;

  // skip header
  if (line.toLowerCase().indexOf("raw_value") === 0) return null;

  // jackie's csv format: raw_value,level_ml,rate_ml_min,state,button,acknowledged,yellow_led,red_led,buzzer
  var parts = line.split(",");
  if (parts.length >= 9) {
    var raw = parseFloat(parts[0]);
    var level = parseFloat(parts[1]);
    var rate = parseFloat(parts[2]);
    if (!isNaN(level)) {
      var levelM = Math.round(level * LEVEL_UNIT_TO_METRES * 100) / 100;
      var rateM = Math.round(rate * LEVEL_UNIT_TO_METRES * 100) / 100;
      return {
        value: levelM,
        label: "water_level",
        extras: {
          raw_distance: raw,
          level_original: level,
          rate_original: rate,
          rate_m_min: rateM,
          state: (parts[3] || "").trim(),
          button: parseInt(parts[4]) || 0,
          acknowledged: parseInt(parts[5]) || 0,
          yellow_led: parseInt(parts[6]) || 0,
          red_led: parseInt(parts[7]) || 0,
          buzzer: parseInt(parts[8]) || 0
        }
      };
    }
  }

  // fallback: label:value or label=value
  var colonMatch = line.match(/^([A-Za-z_]+)\s*[:=]\s*(-?\d+\.?\d*)/);
  if (colonMatch) {
    return { value: parseFloat(colonMatch[2]), label: colonMatch[1], extras: {} };
  }

  // fallback: plain number
  var numMatch = line.match(/^(-?\d+\.?\d*)/);
  if (numMatch) {
    return { value: parseFloat(numMatch[1]), label: "sensor", extras: {} };
  }

  return null;
}

function createLineSplitter() {
  var buffer = "";
  return new TransformStream({
    transform: function (chunk, controller) {
      buffer += chunk;
      var lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (var i = 0; i < lines.length; i++) {
        controller.enqueue(lines[i]);
      }
    },
    flush: function (controller) {
      if (buffer) {
        controller.enqueue(buffer);
      }
    },
  });
}

function initChart() {
  if (!chartCanvas || typeof Chart === "undefined") return;
  if (sensorChart) {
    sensorChart.destroy();
    sensorChart = null;
  }
  sensorChart = new Chart(chartCanvas, {
    type: "line",
    data: {
      labels: ["0", "1"],
      datasets: [
        {
          label: "Water Level",
          data: chartValues,
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.12)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
          fill: true,
          spanGaps: false,
        },
        {
          label: "Warning (" + THRESHOLD_WARNING + "m)",
          data: [THRESHOLD_WARNING, THRESHOLD_WARNING],
          borderColor: "#f59e0b",
          borderWidth: 2,
          borderDash: [6, 6],
          pointRadius: 0,
          fill: false,
          tension: 0,
        },
        {
          label: "Danger (" + THRESHOLD_DANGER + "m)",
          data: [THRESHOLD_DANGER, THRESHOLD_DANGER],
          borderColor: "#dc2626",
          borderWidth: 2,
          borderDash: [6, 6],
          pointRadius: 0,
          fill: false,
          tension: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: { title: { display: true, text: "Time" } },
        y: { title: { display: true, text: "Water Level (m)" }, suggestedMin: 0, suggestedMax: 4 },
      },
    },
  });
}

function setConnStatus(text) {
  if (elConnStatus) elConnStatus.textContent = text;
}

function setButtonsConnected(connected) {
  if (btnConnect) btnConnect.disabled = !serialSupported || connected;
  if (btnDisconnect) btnDisconnect.disabled = !connected;
}

function showError(msg) {
  if (!elErrorLine) return;
  elErrorLine.textContent = msg;
  elErrorLine.classList.remove("hidden");
}

function clearError() {
  if (!elErrorLine) return;
  elErrorLine.textContent = "";
  elErrorLine.classList.add("hidden");
}

function appendPoint(value) {
  var now = new Date();
  var timeStr = now.getHours().toString().padStart(2, '0') + ':' +
                now.getMinutes().toString().padStart(2, '0') + ':' +
                now.getSeconds().toString().padStart(2, '0');
  chartLabels.push(timeStr);
  chartValues.push(value);
  while (chartLabels.length > MAX_POINTS) {
    chartLabels.shift();
    chartValues.shift();
  }
  if (sensorChart) {
    sensorChart.data.labels = chartLabels.length ? chartLabels : ["0", "1"];
    sensorChart.data.datasets[0].data = chartValues;

    
    sensorChart.data.datasets[1].data = chartLabels.length
      ? chartLabels.map(function () { return THRESHOLD_WARNING; })
      : [THRESHOLD_WARNING, THRESHOLD_WARNING];

    
    sensorChart.data.datasets[2].data = chartLabels.length
      ? chartLabels.map(function () { return THRESHOLD_DANGER; })
      : [THRESHOLD_DANGER, THRESHOLD_DANGER];

    
    if (value >= THRESHOLD_DANGER) {
      sensorChart.data.datasets[0].borderColor = "#dc2626";
      sensorChart.data.datasets[0].backgroundColor = "rgba(220, 38, 38, 0.15)";
    } else if (value >= THRESHOLD_WARNING) {
      sensorChart.data.datasets[0].borderColor = "#f59e0b";
      sensorChart.data.datasets[0].backgroundColor = "rgba(245, 158, 11, 0.15)";
    } else {
      sensorChart.data.datasets[0].borderColor = "#2563eb";
      sensorChart.data.datasets[0].backgroundColor = "rgba(37, 99, 235, 0.12)";
    }

    sensorChart.update("none");
  }

  
  var badge = document.getElementById("riskBadge");
  if (badge) {
    if (value >= THRESHOLD_DANGER) {
      badge.innerHTML = '<span class="status-danger">⚠ ABOVE DANGER THRESHOLD</span>';
    } else if (value >= THRESHOLD_WARNING) {
      badge.innerHTML = '<span class="status-warning">⚠ ABOVE WARNING THRESHOLD</span>';
    } else {
      badge.innerHTML = '<span class="status-normal">Normal</span>';
    }
  }
}

function clearChartData() {
  chartLabels.length = 0;
  chartValues.length = 0;
  sampleSeq = 0;
  totalSamples = 0;
  invalidLines = 0;
  if (elLatest) elLatest.textContent = "—";
  if (elSampleCount) elSampleCount.textContent = "0";
  if (elInvalidCount) elInvalidCount.textContent = "0";
  if (sensorChart) {
    sensorChart.data.labels = chartLabels;
    sensorChart.data.datasets[0].data = chartValues;
    sensorChart.data.datasets[1].data = chartLabels.map(function () { return THRESHOLD_WARNING; });
    sensorChart.data.datasets[2].data = chartLabels.map(function () { return THRESHOLD_DANGER; });
    sensorChart.data.datasets[0].borderColor = "#2563eb";
    sensorChart.data.datasets[0].backgroundColor = "rgba(37, 99, 235, 0.12)";
    sensorChart.update("none");
  }
}

async function safeDisconnect() {
  keepReading = false;
  if (readerRef) {
    try { await readerRef.cancel(); } catch (e) { }
    try { readerRef.releaseLock(); } catch (e) { }
    readerRef = null;
  }
  if (readableClosedRef) {
    try { await readableClosedRef; } catch (e) { }
    readableClosedRef = null;
  }
  if (portRef) {
    try { await portRef.close(); } catch (e) { }
    portRef = null;
  }
  setConnStatus("Disconnected");
  setButtonsConnected(false);
}

async function disconnectSerial() {
  keepReading = false;
  await safeDisconnect();
}

async function connectToArduino() {
  clearError();
  if (!("serial" in navigator)) {
    showError("Web Serial is not supported in this browser.");
    return;
  }

  var port;
  try {
    port = await navigator.serial.requestPort();
  } catch (err) {
    if (err && err.name === "NotFoundError") {
      showError("Port selection was cancelled.");
      return;
    }
    showError("Could not select serial port: " + (err && err.message ? err.message : String(err)));
    return;
  }

  try {
    await port.open({ baudRate: BAUD_RATE });
  } catch (err) {
    showError("Could not open serial port: " + (err && err.message ? err.message : String(err)));
    return;
  }

  portRef = port;
  keepReading = true;
  setConnStatus("Connected");
  setButtonsConnected(true);

  try {
    var decoder = new TextDecoderStream();
    readableClosedRef = port.readable.pipeTo(decoder.writable);
    var lineStream = decoder.readable.pipeThrough(createLineSplitter());
    var reader = lineStream.getReader();
    readerRef = reader;
  } catch (err) {
    showError("Could not open serial stream: " + (err && err.message ? err.message : String(err)));
    await safeDisconnect();
    return;
  }

  try {
    while (keepReading) {
      var result = await reader.read();
      if (result.done) break;
      var line = (result.value || "").trim();
      if (!line) continue;

      var parsed = parseSerialLine(line);
      if (!parsed) {
        invalidLines += 1;
        if (elInvalidCount) elInvalidCount.textContent = String(invalidLines);
        continue;
      }

      totalSamples += 1;
      if (elSampleCount) elSampleCount.textContent = String(totalSamples);
      if (elLatest) elLatest.textContent = String(parsed.value);
      setConnStatus("Reading data");

      appendPoint(parsed.value);
      bufferReading(parsed.value, parsed.label, parsed.extras);
    }
  } catch (err) {
    if (keepReading) {
      showError("Serial read error: " + (err && err.message ? err.message : String(err)));
    }
  } finally {
    await safeDisconnect();
  }
}

// sim mode for testing without arduino
var simInterval = null;
var simWaterLevel = 1.0;
var simRising = true;

function startSimulation() {
  if (simInterval) return; 

  var btnSim = document.getElementById("btnSimulate");
  var btnStop = document.getElementById("btnSimStop");
  if (btnSim) btnSim.disabled = true;
  if (btnStop) btnStop.disabled = false;
  setConnStatus("Simulating");

  simInterval = setInterval(function () {
    
    if (simRising) {
      simWaterLevel += 0.02 + Math.random() * 0.04;
      if (simWaterLevel >= 4.0) simRising = false;
    } else {
      simWaterLevel -= 0.02 + Math.random() * 0.04;
      if (simWaterLevel <= 0.5) simRising = true;
    }
    simWaterLevel = Math.round(simWaterLevel * 100) / 100;

    // chart
    totalSamples += 1;
    if (elSampleCount) elSampleCount.textContent = String(totalSamples);
    if (elLatest) elLatest.textContent = String(simWaterLevel);
    appendPoint(simWaterLevel);

    // buffer
    bufferReading(simWaterLevel, "water_level");

  }, 500); // every 0.5 seconds for smooth display
}

function stopSimulation() {
  if (simInterval) {
    clearInterval(simInterval);
    simInterval = null;
  }
  var btnSim = document.getElementById("btnSimulate");
  var btnStop = document.getElementById("btnSimStop");
  if (btnSim) btnSim.disabled = false;
  if (btnStop) btnStop.disabled = true;
  setConnStatus("Simulation stopped");
}
