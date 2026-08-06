import { beforeEach, describe, expect, test } from "bun:test";
import {
  findMerchant,
  getDB,
  merchantPromotions,
  resetDB,
  setMerchantPromotionEnrollment,
} from "./db.js";
import type { Merchant, Promotion } from "./schema/index.js";

describe("database helpers", () => {
  beforeEach(() => resetDB());

  test("merchant numeric ids require a complete match", () => {
    getDB().merchants.set(1, { id: 1, uuid: "merchant-1" } as Merchant);

    expect(findMerchant("1")?.id).toBe(1);
    expect(findMerchant(1)?.id).toBe(1);
    expect(findMerchant("merchant-1")?.id).toBe(1);
    expect(findMerchant("1abc")).toBeUndefined();
  });

  test("promotion enrollment is isolated per merchant", () => {
    getDB().promotions.push({
      id: "promo_1",
      enrollmentStatus: "AVAILABLE",
    } as Promotion);

    setMerchantPromotionEnrollment(1, "promo_1", "JOINED");

    expect(merchantPromotions(1)[0]?.enrollmentStatus).toBe("JOINED");
    expect(merchantPromotions(2)[0]?.enrollmentStatus).toBe("AVAILABLE");
  });
});
