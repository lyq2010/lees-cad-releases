import test from 'node:test';
import assert from 'node:assert/strict';
import {validateReleaseNotes} from './notes-policy.mjs';

test('release notes and changelog accept actual changes', () => {
  assert.doesNotThrow(() => validateReleaseNotes('# 更新日志\n\n- 修复部分 DWG 无法打开的问题。\n- 改善复杂填充显示。'));
  assert.doesNotThrow(() => validateReleaseNotes('- 新增 macOS CLI。\n- 修复 MSI 安装问题。'));
});

test('static distribution, font and signing footer is rejected', () => {
  for (const sentence of [
    'Windows 提供 MSI；macOS 提供 Apple Silicon DMG 和应用更新 TAR。',
    'CLI 随完整安装包提供，与桌面共用全部 80 份字体。',
    'macOS 使用 ad-hoc 签名，非 Developer ID 或 Apple 公证。',
  ]) {
    assert.throws(() => validateReleaseNotes(`- 修复问题。\n\n${sentence}`), /static distribution\/signing footer/);
    assert.throws(() => validateReleaseNotes(sentence.replaceAll(' ', '\n')), /static distribution\/signing footer/);
  }
});
