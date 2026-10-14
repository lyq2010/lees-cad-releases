import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {assets} from './verify.mjs';
const root = process.argv[2], verified = assets(root), p = verified.payload;
const notes = join(root,'release-notes.txt');
writeFileSync(notes,p.notes+'\n');
const result = spawnSync('gh',['release','create',p.releaseId,'--repo','lyq2010/lees-cad-releases','--title',`Lee's CAD ${p.version}`,'--notes-file',notes,...verified.files.values()],{stdio:'inherit'});
if(result.status!==0)throw new Error('Public release creation failed; mirrors remain at the verified release');
