import type { SiteRepository } from "../../src/modules/sites/site.repository.js";
import { InMemorySiteRepository } from "../../src/modules/sites/in-memory-site.repository.js";
import { SiteService } from "../../src/modules/sites/site.service.js";
import { describe, expect, it, vi } from "vitest";

describe("site catalog", () => {
  it("returns the seven initial Bulgarian locations in a stable order", async () => {
    const repository = new InMemorySiteRepository();

    await expect(repository.list()).resolves.toEqual([
      {
        id: 1,
        slug: "sofia-vitosha-kominite",
        name: "Sofia - Vitosha (Kominite)",
        latitude: 42.60222,
        longitude: 23.28927,
      },
      {
        id: 2,
        slug: "zlatitsa",
        name: "Zlatitsa",
        latitude: 42.71506,
        longitude: 24.13749,
      },
      {
        id: 3,
        slug: "sopot",
        name: "Sopot",
        latitude: 42.68776,
        longitude: 24.74996,
      },
      {
        id: 4,
        slug: "nevsha",
        name: "Nevsha",
        latitude: 43.27155,
        longitude: 27.29945,
      },
      {
        id: 5,
        slug: "shumen",
        name: "Shumen",
        latitude: 43.27667,
        longitude: 26.92917,
      },
      {
        id: 6,
        slug: "pastrina",
        name: "Pastrina",
        latitude: 43.42481,
        longitude: 23.30355,
      },
      {
        id: 7,
        slug: "dobrich-region",
        name: "Dobrich region",
        latitude: 43.56667,
        longitude: 27.83333,
      },
    ]);
  });

  it("sorts custom site catalogs by numeric identifier", async () => {
    const repository = new InMemorySiteRepository([
      { id: 7, slug: "last", name: "Last", latitude: 43, longitude: 27 },
      { id: 1, slug: "first", name: "First", latitude: 42, longitude: 23 },
      { id: 4, slug: "middle", name: "Middle", latitude: 43, longitude: 26 },
    ]);

    const sites = await repository.list();

    expect(sites.map((site) => site.id)).toEqual([1, 4, 7]);
  });

  it("looks up a known site without exposing mutable repository state", async () => {
    const repository = new InMemorySiteRepository();
    const first = await repository.findBySlug("sopot");

    expect(first).toEqual({
      id: 3,
      slug: "sopot",
      name: "Sopot",
      latitude: 42.68776,
      longitude: 24.74996,
    });
    if (first !== undefined) {
      first.name = "Changed outside the repository";
    }

    await expect(repository.findBySlug("sopot")).resolves.toEqual({
      id: 3,
      slug: "sopot",
      name: "Sopot",
      latitude: 42.68776,
      longitude: 24.74996,
    });
  });

  it("rejects duplicate numeric site identifiers", () => {
    expect(
      () =>
        new InMemorySiteRepository([
          { id: 3, slug: "sopot", name: "Sopot", latitude: 42, longitude: 24 },
          {
            id: 3,
            slug: "other-sopot",
            name: "Duplicate Sopot",
            latitude: 43,
            longitude: 25,
          },
        ]),
    ).toThrow("Duplicate site ID: 3");
  });

  it("rejects duplicate site slugs", () => {
    expect(
      () =>
        new InMemorySiteRepository([
          { id: 3, slug: "sopot", name: "Sopot", latitude: 42, longitude: 24 },
          {
            id: 8,
            slug: "sopot",
            name: "Duplicate Sopot",
            latitude: 43,
            longitude: 25,
          },
        ]),
    ).toThrow("Duplicate site slug: sopot");
  });

  it("keeps the service dependent on the repository port", async () => {
    const site = {
      id: 3,
      slug: "sopot",
      name: "Sopot",
      latitude: 42.68776,
      longitude: 24.74996,
    };
    const list = vi.fn().mockResolvedValue([site]);
    const findBySlug = vi.fn().mockResolvedValue(site);
    const repository: SiteRepository = {
      list,
      findBySlug,
    };
    const service = new SiteService(repository);

    await expect(service.listSites()).resolves.toEqual([site]);
    await expect(service.findSiteBySlug("sopot")).resolves.toEqual(site);
    expect(list).toHaveBeenCalledOnce();
    expect(findBySlug).toHaveBeenCalledWith("sopot");
  });
});
