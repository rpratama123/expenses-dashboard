import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeAll, describe, expect, it } from 'vitest'
import sharp from 'sharp'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')

beforeAll(async () => { await import('./generate-icons.mjs') })

describe('generated installation icons', () => {
  it.each([['favicon-16x16.png', 16], ['favicon-32x32.png', 32], ['apple-touch-icon.png', 180], ['icons/icon-192.png', 192], ['icons/icon-512.png', 512], ['icons/icon-maskable-512.png', 512]])('%s is %ipx', async (file, size) => {
    const metadata = await sharp(resolve(root, 'public', file)).metadata()
    expect(metadata.width).toBe(size); expect(metadata.height).toBe(size)
  })

  it('preserves the source SVG byte-for-byte', async () => {
    expect(await readFile(resolve(root, 'public/favicon.svg'))).toEqual(await readFile(resolve(root, '../sample/favicon.svg')))
  })

  it.each(['apple-touch-icon.png', 'icons/icon-maskable-512.png'])('%s has an opaque dark-green corner', async (file) => {
    const pixel = await sharp(resolve(root, 'public', file)).ensureAlpha().raw().toBuffer()
    expect([...pixel.subarray(0, 4)]).toEqual([23, 34, 29, 255])
  })
})
