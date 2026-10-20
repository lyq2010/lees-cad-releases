// Final distribution contract; historical ZIP names remain only in cleanup allowlists.
export function artifactNames(target, version) {
  if (target === 'windows-x86_64') return [`lees-cad-${version}-windows-x64.msi`];
  if (target === 'darwin-aarch64') return [`lees-cad-${version}-macos-aarch64.dmg`, `lees-cad-${version}-macos-aarch64.app.tar.gz`];
  throw new Error('Unsupported release target');
}

export function checkArtifactNames(target, version, names) {
  const expected = artifactNames(target, version).sort();
  if (!Array.isArray(names) || names.length !== expected.length || [...names].sort().some((name, i) => name !== expected[i])) {
    throw new Error('Release requires Windows MSI and macOS desktop/CLI bundle only');
  }
}
