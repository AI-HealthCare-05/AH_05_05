const MAX_EDGE = 512;
const prepared = new Map<string, Promise<Blob>>();

/** Remove only near-white pixels connected to an image edge by four-neighbour paths. */
export function removeOuterWhite(frame: ImageData) {
  const { width, height, data } = frame;
  const visited = new Uint8Array(width * height);
  const queue = new Uint32Array(width * height);
  let head = 0;
  let tail = 0;
  function enqueue(x: number, y: number) {
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    const pixel = y * width + x;
    if (visited[pixel]) return;
    visited[pixel] = 1;
    const offset = pixel * 4;
    const red = data[offset], green = data[offset + 1], blue = data[offset + 2];
    if (data[offset + 3] > 0 && red > 224 && green > 224 && blue > 224
      && Math.max(red, green, blue) - Math.min(red, green, blue) < 18) queue[tail++] = pixel;
  }
  for (let x = 0; x < width; x += 1) { enqueue(x, 0); enqueue(x, height - 1); }
  for (let y = 0; y < height; y += 1) { enqueue(0, y); enqueue(width - 1, y); }
  while (head < tail) {
    const pixel = queue[head++];
    data[pixel * 4 + 3] = 0;
    const x = pixel % width, y = Math.floor(pixel / width);
    enqueue(x - 1, y); enqueue(x + 1, y); enqueue(x, y - 1); enqueue(x, y + 1);
  }
  return frame;
}

async function processArt(imageUrl: string): Promise<Blob> {
  // A CORS failure is surfaced to the presenter, never replaced with unprocessed opaque art.
  const response = await fetch(imageUrl, { mode: 'cors', credentials: 'same-origin' });
  if (!response.ok) throw new Error('배지 이미지를 불러오지 못했어요.');
  const source = await response.blob();
  if (source.size > 12 * 1024 * 1024) throw new Error('배지 이미지가 너무 커요.');
  const sourceUrl = URL.createObjectURL(source);
  try {
    const image = new Image();
    image.src = sourceUrl;
    await image.decode();
    const scale = Math.min(1, MAX_EDGE / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) throw new Error('배지 이미지를 준비하지 못했어요.');
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    context.putImageData(removeOuterWhite(context.getImageData(0, 0, canvas.width, canvas.height)), 0, 0);
    return await new Promise<Blob>((resolve, reject) => canvas.toBlob(blob => blob
      ? resolve(blob) : reject(new Error('배지 이미지를 준비하지 못했어요.')), 'image/png'));
  } finally { URL.revokeObjectURL(sourceUrl); }
}

/** One bounded processing promise per URL; failed loads may be retried explicitly. */
export function prepareBadgeArt(imageUrl: string): Promise<Blob> {
  let result = prepared.get(imageUrl);
  if (!result) {
    result = processArt(imageUrl).catch(error => { prepared.delete(imageUrl); throw error; });
    prepared.set(imageUrl, result);
  }
  return result;
}
