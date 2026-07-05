/* XiaoZhi Live — full-duplex-ish voice conversation PWA.
 *
 * Flow per turn (uses the PROVEN "manual" listen protocol):
 *   mic open -> stream Opus frames -> client VAD detects end of speech
 *   -> listen/stop -> receive stt + reply text + reply Opus -> play -> repeat.
 *
 * Audio travels: browser <-> HA WebSocket proxy <-> XiaoZhi Cloud.
 */
(function () {
  "use strict";

  // ---------- Config ----------
  const SILENCE_MS = 1100;   // trailing silence that ends a turn
  const MAX_TURN_MS = 12000; // hard cap on one utterance
  const NOSPEECH_MS = 8000;  // give up if user never speaks
  const START_TH = 0.02;     // RMS threshold for "speech present"

  // ---------- State ----------
  let token = null;
  let ws = null;
  let sessionId = null;
  let recorder = null;
  let demux = null;
  let decoder = null;
  let playCtx = null;
  let vadCtx = null, analyser = null, vadTimer = null;
  let mode = "idle";        // idle | active
  let state = "idle";       // idle | connecting | listening | thinking | speaking
  let sending = false;
  let turnStart = 0, lastVoice = 0, spoke = false;
  let dlFrames = [];        // collected downlink Opus packets
  let curBotEl = null;

  // ---------- DOM ----------
  const $ = (id) => document.getElementById(id);
  const micBtn = $("mic"), statusEl = $("status"), transcript = $("transcript"), connDot = $("conn");

  // ---------- Token ----------
  function resolveToken() {
    const u = new URL(location.href);
    const k = u.searchParams.get("k");
    if (k) { localStorage.setItem("xz_token", k); return k; }
    return localStorage.getItem("xz_token");
  }

  function setupFallback() {
    const box = $("setup");
    box.hidden = false;
    $("setupSave").onclick = () => {
      const v = $("setupLink").value.trim();
      try {
        const t = new URL(v).searchParams.get("k") || v;
        if (t) { localStorage.setItem("xz_token", t); location.href = "./"; }
      } catch (_) { if (v) { localStorage.setItem("xz_token", v); location.href = "./"; } }
    };
  }

  // ---------- UI ----------
  function setState(s) {
    state = s;
    document.body.dataset.state = s;
    const labels = { idle: "Tippen zum Sprechen", connecting: "Verbinde…",
      listening: "Ich höre…", thinking: "Denke nach…", speaking: "Antwortet…" };
    statusEl.textContent = labels[s] || "";
  }
  function addMsg(text, who) {
    const el = document.createElement("div");
    el.className = "msg " + who;
    el.textContent = text;
    transcript.appendChild(el);
    transcript.scrollTop = transcript.scrollHeight;
    return el;
  }

  // ---------- WebSocket ----------
  function wsUrl() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${location.host}/xiaozhi_live/ws?k=${encodeURIComponent(token)}`;
  }

  function connect() {
    return new Promise((resolve, reject) => {
      if (ws && ws.readyState === WebSocket.OPEN) return resolve();
      setState("connecting");
      ws = new WebSocket(wsUrl());
      ws.binaryType = "arraybuffer";
      let helloTimer = setTimeout(() => reject(new Error("hello timeout")), 10000);

      ws.onopen = () => {
        ws.send(JSON.stringify({
          type: "hello", version: 1, features: { mcp: true }, transport: "websocket",
          audio_params: { format: "opus", sample_rate: 16000, channels: 1, frame_duration: 60 },
        }));
      };
      ws.onmessage = (ev) => {
        if (typeof ev.data !== "string") { onBinary(ev.data); return; }
        const d = JSON.parse(ev.data);
        if (d.type === "hello") {
          sessionId = d.session_id; clearTimeout(helloTimer);
          connDot.className = "dot on"; resolve();
        } else {
          onControl(d);
        }
      };
      ws.onerror = () => { connDot.className = "dot err"; };
      ws.onclose = () => {
        connDot.className = "dot"; sessionId = null;
        if (mode === "active") { statusEl.textContent = "Verbindung getrennt"; stopConversation(); }
      };
    });
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(Object.assign({ session_id: sessionId }, obj)));
    }
  }

  // ---------- Downlink (XiaoZhi -> us) ----------
  function onControl(d) {
    if (d.type === "stt" && d.text) {
      addMsg(d.text, "user");
    } else if (d.type === "tts") {
      if (d.state === "start") { dlFrames = []; if (decoder) decoder.reset(); setState("thinking"); }
      if (d.state === "sentence_start" && d.text) {
        curBotEl = addMsg(d.text, "bot");
      }
      if (d.state === "stop") { playResponse(); }
    } else if (d.type === "error") {
      statusEl.textContent = "Fehler: " + (d.message || "unbekannt");
    }
    // 'mcp' and 'llm' (emotion) messages are ignored on the client.
  }

  function onBinary(buf) {
    // Downlink Opus frame (24 kHz). Collect for playback.
    dlFrames.push(new Uint8Array(buf));
  }

  async function playResponse() {
    if (!dlFrames.length) { nextTurn(); return; }
    setState("speaking");
    try {
      const { channelData, samplesDecoded, sampleRate } = decoder.decodeFrames(dlFrames);
      dlFrames = [];
      if (!samplesDecoded) { nextTurn(); return; }
      const buffer = playCtx.createBuffer(1, samplesDecoded, sampleRate);
      buffer.getChannelData(0).set(channelData[0].subarray(0, samplesDecoded));
      const src = playCtx.createBufferSource();
      src.buffer = buffer;
      src.connect(playCtx.destination);
      src.onended = () => { if (mode === "active") nextTurn(); };
      src.start();
    } catch (e) {
      console.error("decode/play failed", e);
      nextTurn();
    }
  }

  // ---------- Uplink (mic -> XiaoZhi) ----------
  async function ensureAudio() {
    if (!playCtx) playCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (playCtx.state === "suspended") await playCtx.resume();
    if (!decoder) {
      const { OpusDecoder } = window["opus-decoder"];
      decoder = new OpusDecoder({ channels: 1 });
      await decoder.ready;
    }
  }

  async function startTurn() {
    if (mode !== "active") return;
    dlFrames = [];
    demux = new OggOpusDemuxer((pkt) => {
      if (sending && ws && ws.readyState === WebSocket.OPEN) ws.send(pkt);
    });
    recorder = new Recorder({
      encoderPath: "vendor/encoderWorker.min.js",
      encoderApplication: 2048,   // OPUS_APPLICATION_VOIP
      encoderFrameSize: 60,
      encoderSampleRate: 16000,
      numberOfChannels: 1,
      streamPages: true,
      maxFramesPerPage: 1,
      recordingGain: 1,
      monitorGain: 0,
      mediaTrackConstraints: {
        echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1,
      },
    });
    recorder.ondataavailable = (page) => demux.push(page);

    await recorder.start();
    sending = true;
    send({ type: "listen", state: "start", mode: "manual" });
    setState("listening");
    startVAD();
  }

  function startVAD() {
    turnStart = Date.now(); lastVoice = 0; spoke = false;
    try {
      if (!vadCtx) vadCtx = new (window.AudioContext || window.webkitAudioContext)();
      const stream = recorder.stream;
      if (!stream) return; // VAD optional; button still ends turn
      const srcNode = vadCtx.createMediaStreamSource(stream);
      analyser = vadCtx.createAnalyser();
      analyser.fftSize = 1024;
      srcNode.connect(analyser);
      const data = new Float32Array(analyser.fftSize);
      vadTimer = setInterval(() => {
        analyser.getFloatTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
        const rms = Math.sqrt(sum / data.length);
        const now = Date.now();
        if (rms > START_TH) { spoke = true; lastVoice = now; }
        const elapsed = now - turnStart;
        if (spoke && lastVoice && now - lastVoice > SILENCE_MS) return endTurn();
        if (elapsed > MAX_TURN_MS) return endTurn();
        if (!spoke && elapsed > NOSPEECH_MS) return endTurn(true);
      }, 60);
    } catch (e) { console.warn("VAD unavailable", e); }
  }

  function stopVAD() {
    if (vadTimer) { clearInterval(vadTimer); vadTimer = null; }
    analyser = null;
  }

  async function endTurn(noSpeech) {
    if (state !== "listening") return;
    stopVAD();
    sending = false;
    try { if (recorder) await recorder.stop(); } catch (_) {}
    recorder = null;
    if (noSpeech) { // nothing was said — go idle instead of pestering the server
      send({ type: "listen", state: "stop" });
      setState("idle"); statusEl.textContent = "Nichts gehört — tippen zum Sprechen";
      mode = "idle"; return;
    }
    send({ type: "listen", state: "stop" });
    setState("thinking");
  }

  function nextTurn() {
    if (mode === "active") startTurn();
  }

  // ---------- Conversation control ----------
  async function startConversation() {
    try {
      await ensureAudio();
      await connect();
      mode = "active";
      startTurn();
    } catch (e) {
      console.error(e);
      statusEl.textContent = "Verbindung fehlgeschlagen";
      setState("idle");
    }
  }

  function stopConversation() {
    mode = "idle";
    stopVAD();
    sending = false;
    try { if (recorder) recorder.stop(); } catch (_) {}
    recorder = null;
    setState("idle");
  }

  // ---------- Button ----------
  micBtn.addEventListener("click", async () => {
    if (mode === "idle") return startConversation();
    // active:
    if (state === "speaking") {          // barge-in: interrupt and listen
      try { await playCtx.suspend(); await playCtx.resume(); } catch (_) {}
      return startTurn();
    }
    if (state === "listening") return endTurn(); // finish speaking now
    stopConversation();                  // otherwise stop the whole session
  });

  // ---------- Boot ----------
  token = resolveToken();
  if (!token) { setupFallback(); }
  else {
    setState("idle");
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    }
  }
})();
