import type { SiteRepository } from "../../src/modules/sites/site.repository.js";
import { InMemorySiteRepository } from "../../src/modules/sites/in-memory-site.repository.js";
import { SiteService } from "../../src/modules/sites/site.service.js";
import { describe, expect, it, vi } from "vitest";

describe("site catalog", () => {
  it("returns the seven initial Bulgarian locations in a stable order", async () => {
    const repository = new InMemorySiteRepository();

    await expect(repository.list()).resolves.toEqual([
      { id: "sofia-vitosha-kominite", name: "Sofia - Vitosha (Kominite)" },
      { id: "zlatitsa", name: "Zlatitsa" },
      { id: "sopot", name: "Sopot" },
      { id: "nevsha", name: "Nevsha" },
      { id: "shumen", name: "Shumen" },
      { id: "pastrona", name: "Pastrona" },
      { id: "dobrich-region", name: "Dobrich region" },
    ]);
  });

  it("looks up a known site without exposing mutable repository state", async () => {
    const repository = new InMemorySiteRepository();
    const first = await repository.findById("sopot");

    expect(first).toEqual({ id: "sopot", name: "Sopot" });
    if (first !== undefined) {
      first.name = "Changed outside the repository";
    }

    await expect(repository.findById("sopot")).resolves.toEqual({ id: "sopot", name: "Sopot" });
  });

  it("rejects duplicate site identifiers", () => {
    expect(
      () =>
        new InMemorySiteRepository([
          { id: "sopot", name: "Sopot" },
          { id: "sopot", name: "Duplicate Sopot" },
        ]),
    ).toThrow("Duplicate site ID: sopot");
  });

  it("keeps the service dependent on the repository port", async () => {
    const list = vi.fn().mockResolvedValue([{ id: "sopot", name: "Sopot" }]);
    const findById = vi.fn().mockResolvedValue({ id: "sopot", name: "Sopot" });
    const repository: SiteRepository = {
      list,
      findById,
    };
    const service = new SiteService(repository);

    await expect(service.listSites()).resolves.toEqual([{ id: "sopot", name: "Sopot" }]);
    await expect(service.findSite("sopot")).resolves.toEqual({ id: "sopot", name: "Sopot" });
    expect(list).toHaveBeenCalledOnce();
    expect(findById).toHaveBeenCalledWith("sopot");
  });
});
