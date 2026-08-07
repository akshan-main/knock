class KnockPCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunkSize = 4096;
    this.chunk = new Float32Array(this.chunkSize);
    this.offset = 0;
  }

  process(inputs) {
    const channels = inputs[0];
    if (!channels || channels.length === 0) return true;

    const input = channels[0];
    let cursor = 0;
    while (cursor < input.length) {
      const available = this.chunkSize - this.offset;
      const count = Math.min(available, input.length - cursor);
      this.chunk.set(input.subarray(cursor, cursor + count), this.offset);
      this.offset += count;
      cursor += count;

      if (this.offset === this.chunkSize) {
        const pcm = this.chunk;
        this.port.postMessage({ pcm: pcm.buffer }, [pcm.buffer]);
        this.chunk = new Float32Array(this.chunkSize);
        this.offset = 0;
      }
    }

    return true;
  }
}

registerProcessor("knock-pcm-processor", KnockPCMProcessor);
