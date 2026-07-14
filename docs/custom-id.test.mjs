// custom-id.test.mjs — proves the browser encoder reproduces WardStone's codec.
//
//     node docs/custom-id.test.mjs        (no dependencies, no network)
//
// custom-id.golden.json is generated FROM WardStone's own encode_custom_id, so if
// every vector here matches, the JavaScript (this repo) and the Python (WardStone)
// implementations agree — a user who checks out will bind the exact subject the gate
// later looks up. If the codec ever changes, regenerate the golden file from WardStone
// and both sides' tests will flag the drift.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { encodeCustomId } from "./custom-id.js";

const here = dirname(fileURLToPath(import.meta.url));
const vectors = JSON.parse(readFileSync(join(here, "custom-id.golden.json"), "utf8"));

let failed = 0;
for (const { product, subject, custom_id } of vectors) {
  const got = encodeCustomId(product, subject);
  const ok = got === custom_id;
  if (!ok) failed++;
  const label = `(${JSON.stringify(product)}, ${JSON.stringify(subject)})`;
  console.log(`${ok ? "ok  " : "FAIL"} ${label} -> ${got}${ok ? "" : `   expected ${custom_id}`}`);
}
console.log(`\n${vectors.length - failed}/${vectors.length} vectors matched WardStone's codec`);
process.exit(failed ? 1 : 0);
