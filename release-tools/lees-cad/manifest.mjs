import {readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {createPrivateKey, createPublicKey, sign, verify} from 'node:crypto';
import {validateReleaseNotes} from './notes-policy.mjs';
const [root, version, revision] = process.argv.slice(2);
const config = JSON.parse(readFileSync(new URL('./public-config.json', import.meta.url)));
const key = createPrivateKey(process.env.LEESCAD_RELEASE_PRIVATE_KEY);
if (createPublicKey(key).export({type:'spki', format:'der'}).subarray(-32).toString('base64') !== config.releasePublicKey) throw new Error('Release signing key mismatch');
const platforms = {};
for (const target of ['windows-x86_64', 'darwin-aarch64']) {
  const row = JSON.parse(readFileSync(join(root, `${target}.json`)));
  if (row.version !== version || row.sourceRevision !== revision || row.target !== target) throw new Error('Platform/source mismatch');
  const {bundleId, minOs, binarySha256, signerCertificateSha256, artifact} = row;
  platforms[target] = {bundleId, minOs, binarySha256, signerCertificateSha256, artifact};
}
const notesFile = new URL(`./notes-${version}.md`, import.meta.url);
const notes = process.env.RELEASE_NOTES ?? readFileSync(notesFile, 'utf8');
validateReleaseNotes(notes);
const payload = {schemaVersion:1, product:'lees-cad', channel:'stable', releaseId:`lees-cad-v${version}`, version, sourceRevision:revision, publishedAt:new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'), notes, platforms};
const bytes = Buffer.from(JSON.stringify(payload)), signature = sign(null, bytes, key);
if (!verify(null, bytes, createPublicKey(key), signature)) throw new Error('Release signature verification failed');
writeFileSync(join(root, 'release-manifest.json'), JSON.stringify({keyId:config.keyId, payloadBase64:bytes.toString('base64'), signatureBase64:signature.toString('base64')}, null, 2) + '\n', {flag:'wx'});
