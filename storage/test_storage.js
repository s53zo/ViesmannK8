const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const run = name => new Function('msg','node', fs.readFileSync(path.join(__dirname,name),'utf8'));
const prepare = run('observation.js'), ack = run('acknowledge.js');
const errors = [], log = {error:e=>errors.push(e),warn:e=>errors.push(e)};
const sample = {device:'vitocal-2048',register:'0500-4',observed_at:'2026-01-01T00:00:00.123456789+00:00',
    quality:'verified',raw_hex:'00990000',counter_value:0,decoder_version:'v1'};
function write(p) {return prepare({topic:'vito/telemetry/v2/'+p.register,payload:p},log);}
const point = write(sample);
assert.equal(point.payload,write(sample).payload);
assert.match(point.payload,/counter_value=0i 1767225600123456789$/);
assert.match(write({...sample,quality:'unknown',text_value:'Heizen',raw_hex:'FFFF'}).payload,/text_value="Heizen"/);
const timeout={...sample,quality:'timeout'};
delete timeout.raw_hex; delete timeout.counter_value;
assert.doesNotMatch(write(timeout).payload,/raw_hex|counter_value/);
assert.equal(write({...sample,observed_at:'2026-02-30T12:00:00Z'}),null);
assert.equal(write({...sample,raw_hex:'\ncorrupt'}),null);
assert.equal(write({...sample,counter_value:1.2}),null);
assert.equal(prepare({topic:'vito/telemetry/v2/0501-4',payload:sample},log),null);
assert.match(write({...sample,register:'_health',backlog:0}).payload,/vito_reader_health_v2,device=vitocal-2048 backlog=0i/);
assert.match(write({...sample,register:'_health',clock_synchronized:1}).payload,/clock_synchronized=1i/);
assert.equal(ack({...point,statusCode:503},log),null);
assert.equal(ack({...point,statusCode:'ETIMEDOUT'},log),null);
assert.deepEqual(JSON.parse(ack({...point,statusCode:204},log).payload),{register:sample.register,observed_at:sample.observed_at});
console.log('Storage conversion, type, retry and acknowledgement checks passed');
