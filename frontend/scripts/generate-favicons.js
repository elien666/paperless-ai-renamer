#!/usr/bin/env node

/**
 * Generate favicons from SVG
 * This script generates PNG favicons in various sizes from the SVG favicon
 * 
 * Usage: node scripts/generate-favicons.js
 * 
 * Requires: sharp (npm install sharp --save-dev)
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Check if sharp is available
let sharp;
try {
  sharp = (await import('sharp')).default;
} catch (e) {
  console.error('Error: sharp is not installed. Please run: npm install sharp --save-dev');
  console.error('Alternatively, you can use an online tool to convert favicon.svg to PNG formats.');
  process.exit(1);
}

const publicDir = path.join(__dirname, '..', 'public');
const svgPath = path.join(publicDir, 'favicon.svg');

if (!fs.existsSync(svgPath)) {
  console.error(`Error: ${svgPath} not found`);
  process.exit(1);
}

const sizes = [
  { size: 16, name: 'favicon-16x16.png' },
  { size: 32, name: 'favicon-32x32.png' },
  { size: 180, name: 'apple-touch-icon.png' },
];

async function generateFavicons() {
  console.log('Generating favicons from SVG...');
  
  for (const { size, name } of sizes) {
    try {
      await sharp(svgPath)
        .resize(size, size)
        .png()
        .toFile(path.join(publicDir, name));
      console.log(`✓ Generated ${name} (${size}x${size})`);
    } catch (error) {
      console.error(`✗ Failed to generate ${name}:`, error.message);
    }
  }
  
  // Generate web manifest
  const manifest = {
    name: 'Paperless AI Renamer',
    short_name: 'AI Renamer',
    icons: [
      {
        src: '/favicon-16x16.png',
        sizes: '16x16',
        type: 'image/png'
      },
      {
        src: '/favicon-32x32.png',
        sizes: '32x32',
        type: 'image/png'
      },
      {
        src: '/apple-touch-icon.png',
        sizes: '180x180',
        type: 'image/png'
      }
    ],
    theme_color: '#3b82f6',
    background_color: '#ffffff',
    display: 'standalone'
  };
  
  fs.writeFileSync(
    path.join(publicDir, 'site.webmanifest'),
    JSON.stringify(manifest, null, 2)
  );
  console.log('✓ Generated site.webmanifest');
  
  console.log('\nAll favicons generated successfully!');
}

generateFavicons().catch(console.error);

