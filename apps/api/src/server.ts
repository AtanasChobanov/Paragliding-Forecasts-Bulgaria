import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import type { Express } from "express";

export interface StartServerOptions {
  readonly app: Express;
  readonly host: string;
  readonly port: number;
  readonly gracePeriodMs?: number;
}

export interface RunningServer {
  readonly address: AddressInfo;
  readonly server: Server;
  close(): Promise<void>;
}

const createClose = (server: Server, gracePeriodMs: number): (() => Promise<void>) => {
  let closePromise: Promise<void> | undefined;

  return () => {
    closePromise ??= new Promise<void>((resolve, reject) => {
      const forceCloseTimer = setTimeout(() => {
        server.closeAllConnections();
      }, gracePeriodMs);
      forceCloseTimer.unref();

      server.close((error) => {
        clearTimeout(forceCloseTimer);

        if (error === undefined) {
          resolve();
          return;
        }

        reject(error);
      });
    });

    return closePromise;
  };
};

export const startServer = ({
  app,
  host,
  port,
  gracePeriodMs = 10_000,
}: StartServerOptions): Promise<RunningServer> =>
  new Promise((resolve, reject) => {
    const server = createServer(app);

    const handleStartupError = (error: Error): void => {
      reject(error);
    };

    server.once("error", handleStartupError);
    server.listen(port, host, () => {
      server.off("error", handleStartupError);
      const address = server.address();

      if (address === null || typeof address === "string") {
        void createClose(server, gracePeriodMs)();
        reject(new Error("The API server did not bind to a TCP address."));
        return;
      }

      resolve({
        address,
        server,
        close: createClose(server, gracePeriodMs),
      });
    });
  });
