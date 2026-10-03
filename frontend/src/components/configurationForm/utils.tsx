export const formatConnectionAddress = (url: string): string => {
  const { hostname, port } = new URL(url);
  // Plex encodes an IPv4 address in its TLS hostname. Other connections may
  // use ordinary DNS names, IPv4 literals or bracketed IPv6 addresses.
  const plexIp = /^(\d{1,3}-\d{1,3}-\d{1,3}-\d{1,3})\..+\.plex\.direct$/i.exec(
    hostname,
  );
  const address = plexIp ? plexIp[1].replace(/-/g, '.') : hostname;
  return port ? `${address}:${port}` : address;
};
