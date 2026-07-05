/* Streaming Ogg demuxer: extracts raw Opus packets from opus-recorder output.
 *
 * opus-recorder emits an Ogg Opus stream (with streamPages:true it arrives
 * incrementally). XiaoZhi expects RAW Opus packets, so we strip the Ogg
 * container here: parse pages, reassemble packets across lacing/pages, and
 * skip the OpusHead / OpusTags header packets.
 */
(function (global) {
  "use strict";

  function concat(a, b) {
    const out = new Uint8Array(a.length + b.length);
    out.set(a, 0);
    out.set(b, a.length);
    return out;
  }

  class OggOpusDemuxer {
    constructor(onPacket) {
      this.onPacket = onPacket;
      this.buf = new Uint8Array(0);
      this.partial = null;      // packet bytes continued across pages
      this.headerPackets = 0;   // OpusHead + OpusTags to skip
    }

    push(chunk) {
      this.buf = concat(this.buf, chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk));
      this._parse();
    }

    _parse() {
      let off = 0;
      const b = this.buf;
      while (true) {
        // Need the fixed 27-byte page header.
        if (b.length - off < 27) break;
        // Resync to capture pattern if needed.
        if (!(b[off] === 0x4f && b[off + 1] === 0x67 && b[off + 2] === 0x67 && b[off + 3] === 0x53)) {
          off++;
          continue;
        }
        const nsegs = b[off + 26];
        const segStart = off + 27;
        if (b.length - segStart < nsegs) break;
        const segTable = b.subarray(segStart, segStart + nsegs);
        let bodyLen = 0;
        for (let i = 0; i < nsegs; i++) bodyLen += segTable[i];
        const bodyStart = segStart + nsegs;
        if (b.length - bodyStart < bodyLen) break; // wait for full page

        // Split body into packets via lacing values.
        let p = bodyStart;
        let cur = this.partial || new Uint8Array(0);
        for (let i = 0; i < nsegs; i++) {
          const s = segTable[i];
          cur = concat(cur, b.subarray(p, p + s));
          p += s;
          if (s < 255) {
            this._emit(cur);
            cur = new Uint8Array(0);
          }
        }
        // A trailing 255 lacing means the packet continues on the next page.
        this.partial = cur.length > 0 && segTable[nsegs - 1] === 255 ? cur : null;
        off = bodyStart + bodyLen;
      }
      this.buf = off > 0 ? b.subarray(off) : b;
    }

    _emit(packet) {
      if (packet.length === 0) return;
      if (this.headerPackets < 2) {
        // Skip OpusHead / OpusTags.
        const isHead = packet.length >= 8 &&
          packet[0] === 0x4f && packet[1] === 0x70 && packet[2] === 0x75 && packet[3] === 0x73; // "Opus"
        if (isHead) { this.headerPackets++; return; }
      }
      this.onPacket(packet);
    }
  }

  global.OggOpusDemuxer = OggOpusDemuxer;
})(window);
