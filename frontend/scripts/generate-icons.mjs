import { copyFile, mkdir, readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const here = dirname(fileURLToPath(import.meta.url))
const source = resolve(here, '../../sample/favicon.svg')
const publicDir = resolve(here, '../public')
const iconsDir = resolve(publicDir, 'icons')
const green = { r: 23, g: 34, b: 29, alpha: 1 }

await mkdir(iconsDir, { recursive: true })
await copyFile(source, resolve(publicDir, 'favicon.svg'))
const svg = await readFile(source)

await Promise.all([
  sharp(svg).resize(16, 16).png().toFile(resolve(publicDir, 'favicon-16x16.png')),
  sharp(svg).resize(32, 32).png().toFile(resolve(publicDir, 'favicon-32x32.png')),
  sharp(svg).resize(180, 180).flatten({ background: green }).png().toFile(resolve(publicDir, 'apple-touch-icon.png')),
  sharp(svg).resize(192, 192).png().toFile(resolve(iconsDir, 'icon-192.png')),
  sharp(svg).resize(512, 512).png().toFile(resolve(iconsDir, 'icon-512.png')),
  sharp({ create: { width: 512, height: 512, channels: 4, background: green } })
    .composite([{ input: await sharp(svg).resize(410, 410).png().toBuffer(), left: 51, top: 51 }])
    .png().toFile(resolve(iconsDir, 'icon-maskable-512.png')),
])
