/**
 * Reader and forward pass for glyphsketch-model.bin (spec: docs/export_format.md).
 * Weights are dequantized once at load; inference runs in float32 on (C, H, W) tensors.
 */

const MODEL_MAGIC = "GSKM";
const FORMAT_VERSION = 1;

export type Operation =
  | {
      kind: "conv";
      inChannels: number;
      outChannels: number;
      kernel: number;
      stride: number;
      groups: number;
      relu6: boolean;
      weight: Float32Array; // [out][in / groups][ky][kx]
      bias: Float32Array;
    }
  | { kind: "residualBegin" }
  | { kind: "residualAdd" }
  | { kind: "globalAveragePool" }
  | { kind: "linear"; inFeatures: number; outFeatures: number; weight: Float32Array; bias: Float32Array }
  | { kind: "l2Normalize" };

export interface Model {
  inputSize: number;
  embeddingDim: number;
  operations: Operation[];
}

class Reader {
  offset = 0;
  private readonly buffer: ArrayBuffer;
  private readonly view: DataView;

  constructor(buffer: ArrayBuffer) {
    this.buffer = buffer;
    this.view = new DataView(buffer);
  }

  u8(): number {
    return this.view.getUint8(this.offset++);
  }

  u16(): number {
    const value = this.view.getUint16(this.offset, true);
    this.offset += 2;
    return value;
  }

  u32(): number {
    const value = this.view.getUint32(this.offset, true);
    this.offset += 4;
    return value;
  }

  align(): void {
    this.offset += (4 - (this.offset % 4)) % 4;
  }

  bytes(count: number): Uint8Array {
    const bytes = new Uint8Array(this.buffer, this.offset, count);
    this.offset += count;
    return bytes;
  }

  int8(count: number): Int8Array {
    const values = new Int8Array(this.buffer, this.offset, count);
    this.offset += count;
    return values;
  }

  float32(count: number): Float32Array {
    if (this.offset % 4 !== 0) {
      throw new Error(`Unaligned float32 array at byte ${this.offset}`);
    }
    // Little-endian hosts (all current browsers and Android) can view the bytes in place;
    // copy so the result does not pin the file's buffer.
    const values = new Float32Array(count);
    for (let index = 0; index < count; index++) {
      values[index] = this.view.getFloat32(this.offset + 4 * index, true);
    }
    this.offset += 4 * count;
    return values;
  }

  get length(): number {
    return this.buffer.byteLength;
  }
}

export function checkMagic(reader: Reader, magic: string, what: string): void {
  const bytes = reader.bytes(4);
  if (String.fromCharCode(...bytes) !== magic) {
    throw new Error(`Not a glyphsketch ${what} file`);
  }
}

function readQuantized(reader: Reader, outputs: number, perOutput: number): { weight: Float32Array; bias: Float32Array } {
  const values = reader.int8(outputs * perOutput);
  reader.align();
  const scales = reader.float32(outputs);
  const bias = reader.float32(outputs);
  const weight = new Float32Array(outputs * perOutput);
  for (let output = 0; output < outputs; output++) {
    const scale = scales[output]!;
    for (let index = 0; index < perOutput; index++) {
      weight[output * perOutput + index] = values[output * perOutput + index]! * scale;
    }
  }
  return { weight, bias };
}

export function readModel(buffer: ArrayBuffer): Model {
  const reader = new Reader(buffer);
  checkMagic(reader, MODEL_MAGIC, "model");
  const version = reader.u16();
  if (version !== FORMAT_VERSION) {
    throw new Error(`Unsupported model format version ${version}`);
  }
  const inputSize = reader.u16();
  const embeddingDim = reader.u16();
  const count = reader.u16();
  const operations: Operation[] = [];
  for (let index = 0; index < count; index++) {
    const kind = reader.u8();
    if (kind === 1) {
      const inChannels = reader.u16();
      const outChannels = reader.u16();
      const kernel = reader.u8();
      const stride = reader.u8();
      const groups = reader.u16();
      const relu6 = reader.u8() === 1;
      reader.align();
      if (groups !== 1 && (groups !== inChannels || groups !== outChannels)) {
        throw new Error("Only dense and depthwise convolutions are supported");
      }
      const perOutput = (inChannels / groups) * kernel * kernel;
      const { weight, bias } = readQuantized(reader, outChannels, perOutput);
      operations.push({ kind: "conv", inChannels, outChannels, kernel, stride, groups, relu6, weight, bias });
    } else if (kind === 5) {
      const inFeatures = reader.u16();
      const outFeatures = reader.u16();
      reader.align();
      const { weight, bias } = readQuantized(reader, outFeatures, inFeatures);
      operations.push({ kind: "linear", inFeatures, outFeatures, weight, bias });
    } else if (kind === 2) {
      operations.push({ kind: "residualBegin" });
    } else if (kind === 3) {
      operations.push({ kind: "residualAdd" });
    } else if (kind === 4) {
      operations.push({ kind: "globalAveragePool" });
    } else if (kind === 6) {
      operations.push({ kind: "l2Normalize" });
    } else {
      throw new Error(`Unknown operation kind ${kind}`);
    }
  }
  if (reader.offset !== reader.length) {
    throw new Error("Trailing bytes after the last operation");
  }
  return { inputSize, embeddingDim, operations };
}

interface Tensor {
  channels: number;
  size: number; // height = width
  data: Float32Array;
}

/**
 * 1×1 convolution, most of the work: output[o][p] = bias[o] + Σ_c weight[o][c] · input[c][p].
 * Blocked 4 outputs × 4 inputs, so every loaded input value feeds four accumulators.
 */
function pointwise(
  source: Float32Array,
  inChannels: number,
  outChannels: number,
  pixels: number,
  weight: Float32Array,
  bias: Float32Array,
  output: Float32Array,
): void {
  for (let out = 0; out < outChannels; out++) {
    output.fill(bias[out]!, out * pixels, (out + 1) * pixels);
  }
  let out = 0;
  for (; out + 4 <= outChannels; out += 4) {
    const t0 = out * pixels;
    const t1 = t0 + pixels;
    const t2 = t1 + pixels;
    const t3 = t2 + pixels;
    const w0 = out * inChannels;
    const w1 = w0 + inChannels;
    const w2 = w1 + inChannels;
    const w3 = w2 + inChannels;
    let channel = 0;
    for (; channel + 4 <= inChannels; channel += 4) {
      const s0 = channel * pixels;
      const s1 = s0 + pixels;
      const s2 = s1 + pixels;
      const s3 = s2 + pixels;
      const a0 = weight[w0 + channel]!, a1 = weight[w0 + channel + 1]!;
      const a2 = weight[w0 + channel + 2]!, a3 = weight[w0 + channel + 3]!;
      const b0 = weight[w1 + channel]!, b1 = weight[w1 + channel + 1]!;
      const b2 = weight[w1 + channel + 2]!, b3 = weight[w1 + channel + 3]!;
      const c0 = weight[w2 + channel]!, c1 = weight[w2 + channel + 1]!;
      const c2 = weight[w2 + channel + 2]!, c3 = weight[w2 + channel + 3]!;
      const d0 = weight[w3 + channel]!, d1 = weight[w3 + channel + 1]!;
      const d2 = weight[w3 + channel + 2]!, d3 = weight[w3 + channel + 3]!;
      for (let pixel = 0; pixel < pixels; pixel++) {
        const x0 = source[s0 + pixel]!;
        const x1 = source[s1 + pixel]!;
        const x2 = source[s2 + pixel]!;
        const x3 = source[s3 + pixel]!;
        output[t0 + pixel] = output[t0 + pixel]! + a0 * x0 + a1 * x1 + a2 * x2 + a3 * x3;
        output[t1 + pixel] = output[t1 + pixel]! + b0 * x0 + b1 * x1 + b2 * x2 + b3 * x3;
        output[t2 + pixel] = output[t2 + pixel]! + c0 * x0 + c1 * x1 + c2 * x2 + c3 * x3;
        output[t3 + pixel] = output[t3 + pixel]! + d0 * x0 + d1 * x1 + d2 * x2 + d3 * x3;
      }
    }
    for (; channel < inChannels; channel++) {
      const from = channel * pixels;
      const a = weight[w0 + channel]!, b = weight[w1 + channel]!;
      const c = weight[w2 + channel]!, d = weight[w3 + channel]!;
      for (let pixel = 0; pixel < pixels; pixel++) {
        const x = source[from + pixel]!;
        output[t0 + pixel] = output[t0 + pixel]! + a * x;
        output[t1 + pixel] = output[t1 + pixel]! + b * x;
        output[t2 + pixel] = output[t2 + pixel]! + c * x;
        output[t3 + pixel] = output[t3 + pixel]! + d * x;
      }
    }
  }
  for (; out < outChannels; out++) {
    const target = out * pixels;
    for (let channel = 0; channel < inChannels; channel++) {
      const w = weight[out * inChannels + channel]!;
      const from = channel * pixels;
      for (let pixel = 0; pixel < pixels; pixel++) {
        output[target + pixel] = output[target + pixel]! + w * source[from + pixel]!;
      }
    }
  }
}

/** Depthwise convolution; interior pixels skip the bounds checks. */
function depthwise(
  source: Float32Array,
  channels: number,
  inSize: number,
  outSize: number,
  kernel: number,
  stride: number,
  weight: Float32Array,
  bias: Float32Array,
  output: Float32Array,
): void {
  const pad = Math.floor(kernel / 2);
  const taps = kernel * kernel;
  // Output rows/columns whose whole window lies inside the input.
  const first = Math.ceil(pad / stride);
  const last = Math.floor((inSize - kernel + pad) / stride);
  for (let channel = 0; channel < channels; channel++) {
    const base = channel * inSize * inSize;
    const target = channel * outSize * outSize;
    const w = weight.subarray(channel * taps, (channel + 1) * taps);
    const b = bias[channel]!;
    for (let row = 0; row < outSize; row++) {
      const interiorRow = row >= first && row <= last;
      for (let column = 0; column < outSize; column++) {
        let sum = b;
        if (interiorRow && column >= first && column <= last) {
          let origin = base + (row * stride - pad) * inSize + (column * stride - pad);
          for (let ky = 0; ky < kernel; ky++, origin += inSize) {
            for (let kx = 0; kx < kernel; kx++) sum += w[ky * kernel + kx]! * source[origin + kx]!;
          }
        } else {
          for (let ky = 0; ky < kernel; ky++) {
            const y = row * stride + ky - pad;
            if (y < 0 || y >= inSize) continue;
            for (let kx = 0; kx < kernel; kx++) {
              const x = column * stride + kx - pad;
              if (x < 0 || x >= inSize) continue;
              sum += w[ky * kernel + kx]! * source[base + y * inSize + x]!;
            }
          }
        }
        output[target + row * outSize + column] = sum;
      }
    }
  }
}

function convolve(input: Tensor, operation: Extract<Operation, { kind: "conv" }>): Tensor {
  const { kernel, stride, outChannels, weight, bias, relu6 } = operation;
  const pad = Math.floor(kernel / 2);
  const inSize = input.size;
  const outSize = Math.ceil(inSize / stride);
  const outPixels = outSize * outSize;
  const output = new Float32Array(outChannels * outPixels);
  const source = input.data;
  if (kernel === 1 && stride === 1 && operation.groups === 1) {
    pointwise(source, input.channels, outChannels, outPixels, weight, bias, output);
  } else if (operation.groups === 1) {
    const inChannels = input.channels;
    for (let out = 0; out < outChannels; out++) {
      for (let row = 0; row < outSize; row++) {
        for (let column = 0; column < outSize; column++) {
          let sum = bias[out]!;
          for (let channel = 0; channel < inChannels; channel++) {
            for (let ky = 0; ky < kernel; ky++) {
              const y = row * stride + ky - pad;
              if (y < 0 || y >= inSize) continue;
              for (let kx = 0; kx < kernel; kx++) {
                const x = column * stride + kx - pad;
                if (x < 0 || x >= inSize) continue;
                sum += weight[((out * inChannels + channel) * kernel + ky) * kernel + kx]! * source[(channel * inSize + y) * inSize + x]!;
              }
            }
          }
          output[out * outPixels + row * outSize + column] = sum;
        }
      }
    }
  } else {
    depthwise(source, outChannels, inSize, outSize, kernel, stride, weight, bias, output);
  }
  if (relu6) {
    for (let index = 0; index < output.length; index++) {
      const value = output[index]!;
      output[index] = value < 0 ? 0 : value > 6 ? 6 : value;
    }
  }
  return { channels: outChannels, size: outSize, data: output };
}

/** Embedding of one image: pixels 0–255 (ink = 255), row-major, inputSize². */
export function embed(model: Model, image: Uint8Array): Float32Array {
  const size = model.inputSize;
  if (image.length !== size * size) {
    throw new Error(`Expected a ${size}×${size} image`);
  }
  let tensor: Tensor = { channels: 1, size, data: Float32Array.from(image, (pixel) => pixel / 255) };
  let vector: Float32Array | null = null;
  const saved: Tensor[] = [];
  for (const operation of model.operations) {
    switch (operation.kind) {
      case "conv":
        tensor = convolve(tensor, operation);
        break;
      case "residualBegin":
        saved.push(tensor);
        break;
      case "residualAdd": {
        const other = saved.pop()!;
        const sum = new Float32Array(tensor.data.length);
        for (let index = 0; index < sum.length; index++) sum[index] = tensor.data[index]! + other.data[index]!;
        tensor = { ...tensor, data: sum };
        break;
      }
      case "globalAveragePool": {
        const pixels = tensor.size * tensor.size;
        vector = new Float32Array(tensor.channels);
        for (let channel = 0; channel < tensor.channels; channel++) {
          let sum = 0;
          for (let pixel = 0; pixel < pixels; pixel++) sum += tensor.data[channel * pixels + pixel]!;
          vector[channel] = sum / pixels;
        }
        break;
      }
      case "linear": {
        const input = vector!;
        const result = new Float32Array(operation.outFeatures);
        for (let out = 0; out < operation.outFeatures; out++) {
          let sum = operation.bias[out]!;
          for (let feature = 0; feature < operation.inFeatures; feature++) {
            sum += operation.weight[out * operation.inFeatures + feature]! * input[feature]!;
          }
          result[out] = sum;
        }
        vector = result;
        break;
      }
      case "l2Normalize": {
        const input: Float32Array = vector!;
        let norm = 0;
        for (const value of input) norm += value * value;
        norm = Math.max(Math.sqrt(norm), 1e-12);
        vector = input.map((value: number) => value / norm);
        break;
      }
    }
  }
  if (vector === null) {
    throw new Error("The model has no pooling layer");
  }
  return vector;
}

export { Reader };
