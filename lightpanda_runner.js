import { lightpanda } from '@lightpanda/browser';

const host = process.env.CDP_HOST || '127.0.0.1';
const port = Number(process.env.CDP_PORT || 9222);

const proc = await lightpanda.serve({ host, port });
console.log(`Lightpanda CDP running at ws://${host}:${port}`);
console.log('Use browser_assist.py from another process to open the manual signup page.');

const stop = () => {
  try {
    proc.stdout?.destroy();
    proc.stderr?.destroy();
    proc.kill();
  } finally {
    process.exit(0);
  }
};

process.on('SIGINT', stop);
process.on('SIGTERM', stop);
await new Promise(() => {});
