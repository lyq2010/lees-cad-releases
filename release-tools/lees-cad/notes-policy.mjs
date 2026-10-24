import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const footer = [
  'Windows 提供 MSI；macOS 提供 Apple Silicon DMG 和应用更新 TAR。',
  'CLI 随完整安装包提供，与桌面共用全部 80 份字体。',
  'macOS 使用 ad-hoc 签名，非 Developer ID 或 Apple 公证。',
];
const compact = text => text.replace(/\s+/g, '');

export function validateReleaseNotes(text) {
  if (footer.some(sentence => compact(text).includes(compact(sentence)))) {
    throw new Error('Remove the static distribution/signing footer; release notes and changelog contain changes only.');
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  validateReleaseNotes(readFileSync(process.argv[2], 'utf8'));
  console.log('Release notes/changelog policy verified');
}
