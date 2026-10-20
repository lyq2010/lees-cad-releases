import {test} from 'node:test';
import assert from 'node:assert/strict';
import {artifactNames, checkArtifactNames} from './artifact-contract.mjs';

test('both platforms accept only the complete current distribution', () => {
  for (const target of ['windows-x86_64', 'darwin-aarch64']) {
    const names = artifactNames(target, '0.1.7');
    assert.doesNotThrow(() => checkArtifactNames(target, '0.1.7', names));
    assert.throws(() => checkArtifactNames(target, '0.1.7', names.slice(1)));
    assert.throws(() => checkArtifactNames(target, '0.1.7', [...names, names[0]]));
    assert.throws(() => checkArtifactNames(target, '0.1.7', [...names, 'lees-cad-cli-0.1.7-macos-aarch64.zip']));
  }
});
