const production = process.env.NODE_ENV === 'production';
const secret = process.env.JWT_SECRET;
if (!secret || secret.length < 32) {
    throw new Error('JWT_SECRET deve conter pelo menos 32 caracteres.');
}
const trustProxy = process.env.TRUST_PROXY || 'false';
const { isIP } = require('node:net');
if (trustProxy !== 'false' && !trustProxy.split(',').every(item => {
    const value = item.trim();
    if (value === 'loopback') return true;
    const [ip, prefix, extra] = value.split('/');
    const version = isIP(ip);
    return version && extra === undefined && (prefix === undefined ||
        (/^\d+$/.test(prefix) && Number(prefix) > 0 && Number(prefix) <= (version === 4 ? 32 : 128)));
})) throw new Error('TRUST_PROXY deve ser false, loopback ou IPs/CIDRs explícitos.');
module.exports = { production, secret, trustProxy: trustProxy === 'false' ? false : trustProxy };
