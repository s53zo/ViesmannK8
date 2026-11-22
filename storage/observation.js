// Node-RED Function body. The timestamp and bounded identity determine the Influx point.
function prepare() {
    const p = msg.payload;
    if (!p || typeof p !== 'object' || Array.isArray(p)) throw Error('expected JSON object');
    const topicKey = msg.topic.split('/').pop();
    if (!/^([0-9A-F]{4}-[1-9][0-9]{0,3}|_health)$/.test(topicKey) || topicKey !== p.register)
        throw Error('register mismatch');
    if (!/^[a-zA-Z0-9_-]{1,64}$/.test(p.device) || typeof p.device !== 'string')
        throw Error('invalid device');

    // JS Date has millisecond resolution. Parse the fraction separately to retain the original identity.
    const ts = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(?:Z|\+00:00)$/.exec(p.observed_at);
    if (!ts) throw Error('timestamp must be ISO UTC');
    const base = new Date(ts[1] + 'Z');
    if (!Number.isFinite(base.getTime()) || base.toISOString().slice(0,19) !== ts[1])
        throw Error('invalid date');
    const nanos = BigInt(base.getTime()) * 1000000n + BigInt((ts[2] || '').padEnd(9, '0'));
    if (nanos < -9223372036854775806n || nanos > 9223372036854775806n)
        throw Error('timestamp outside Influx range');

    const fields = [];
    function string(key) {
        if (p[key] === undefined || p[key] === null) return;
        const value = p[key];
        if (typeof value !== 'string' || value.length > 8192 || /[\r\n\0]/.test(value))
            throw Error('invalid string field: ' + key);
        fields.push(key + '="' + value.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"');
    }
    function number(key, integer = false) {
        if (p[key] === undefined || p[key] === null) return;
        const value = p[key];
        if (!Number.isFinite(value) || (integer && !Number.isSafeInteger(value)))
            throw Error('invalid numeric field: ' + key);
        fields.push(key + '=' + value + (integer ? 'i' : ''));
    }
    let series;
    if (p.register === '_health') {
        series = 'vito_reader_health_v2,device=' + p.device;
        for (const key of ['reads_ok','reads_failed','backlog','dropped','catalogue_size','attempted_registers','clock_synchronized'])
            number(key, true);
        for (const key of ['last_latency_ms','max_fast_lateness_s','last_success_age_s','oldest_backlog_age_s'])
            number(key);
    } else {
        series = 'vito_observation_v2,device=' + p.device + ',register=' + p.register;
        if (!p.quality || !p.decoder_version) throw Error('missing quality or decoder version');
        for (const key of ['quality','decoder_version','raw_hex','text_value','name','tier','confidence'])
            string(key);
        number('numeric_value');
        number('counter_value', true);
        number('latency_ms');
    }
    if (!fields.length) throw Error('no fields');
    msg.vitoAck = {device:p.device, register:p.register, observed_at:p.observed_at};
    msg.headers = {'Content-Type':'text/plain; charset=utf-8'};
    msg.payload = series + ' ' + fields.join(',') + ' ' + nanos.toString();
    return msg;
}
try {
    return prepare();
} catch (err) {
    node.error('Rejected telemetry: ' + err.message);
    return null;
}
