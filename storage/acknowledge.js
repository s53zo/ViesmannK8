if (msg.statusCode !== 204) {
    node.warn('Influx write failed (' + msg.statusCode + '); collector retains sample');
    return null;
}
const a = msg.vitoAck;
return {
    topic: 'vito/ack/v2/' + a.device,
    payload: JSON.stringify({register:a.register, observed_at:a.observed_at}),
    qos: 1,
    retain: false
};
