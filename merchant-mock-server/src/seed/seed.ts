// ── Seed orchestrator ──────────────────────────────────────────────
// Genera un dataset determinista y coherente:
// 5 merchants → stores → empleados → órdenes (con cuotas/pagos)
// → conciliaciones diarias → reportes mensuales + payouts + facturas
// → promociones, productos, POS, payment methods, onboarding.

import { initFaker, f } from "./faker.js";
import { resetIdCounter } from "../utils/id.js";
import {
  resetOrderNumbers,
  uuid,
  vePhone,
  veCedula,
  veBankReference,
  veBank,
  veCity,
  veAddress,
  veFullName,
  veEmail,
  money,
  randInt,
  pick,
  pickN,
  weighted,
  nowISO,
  isoDaysAgo,
  isoDaysFromNow,
  dateKey,
  daysAgoKey,
  toVES,
} from "./generators.js";
import { MERCHANTS, PRODUCT_CATEGORIES, CANCELLATION_REASONS } from "./catalogs.js";
import { applyScenarios } from "./scenarios/index.js";
import { setDB, getDB, type Database } from "../db.js";
import type {
  Merchant,
  Store,
  Employee,
  Order,
  OrderInstallment,
  DailyConciliation,
  MonthlyReport,
  Payout,
  Invoice,
  Promotion,
  POS,
  PaymentMethod,
  Product,
  InventoryJob,
  Onboarding,
  Report,
  Movement,
} from "../schema/index.js";

// ── Run seed ───────────────────────────────────────────────────────

let orderNumCounter = 0;

export function runSeed(): void {
  initFaker();
  resetIdCounter();
  resetOrderNumbers();
  orderNumCounter = 0;

  const db: Database = {
    merchants: new Map(),
    stores: new Map(),
    employees: new Map(),
    orders: new Map(),
    installments: [],
    dailyConciliations: [],
    monthlyReports: [],
    payouts: [],
    invoices: [],
    promotions: [],
    promotionEnrollments: new Map(),
    otpChallenges: new Map(),
    pos: [],
    paymentMethods: [],
    products: [],
    inventoryJobs: [],
    onboardings: new Map(),
    reports: [],
    movements: [],
  };

  // ── 1. Merchants ────────────────────────────────────────────────
  for (const seed of MERCHANTS) {
    const merchant: Merchant = {
      id: seed.id,
      uuid: uuid(),
      rif: seed.rif,
      legalName: seed.legalName,
      tradeName: seed.tradeName,
      categoryId: seed.categoryId,
      model: seed.model,
      merchantGroup: null,
      status: seed.status,
      activeFcb: seed.status === "ACTIVE",
      fcbPeriod: seed.fcbPeriod,
      fcbStartDate: isoDaysAgo(365),
      adminEmail: seed.adminEmail,
      createdAt: isoDaysAgo(365 + randInt(0, 200)),
      scenarioTags: [],
    };
    db.merchants.set(merchant.id, merchant);
  }

  // ── 2. Stores ───────────────────────────────────────────────────
  let storeIdCounter = 1;
  for (const merchant of db.merchants.values()) {
    const storeCount = randInt(1, 3);
    for (let i = 0; i < storeCount; i++) {
      const storeUuid = uuid();
      const isMain = i === 0;
      const store: Store = {
        id: storeIdCounter++,
        uuid: storeUuid,
        merchantId: merchant.id,
        name: isMain
          ? `${merchant.tradeName} - Sede Principal`
          : `${merchant.tradeName} - Sucursal ${i + 1}`,
        email: `${merchant.adminEmail.split("@")[0]}${i > 0 ? `.${i + 1}` : ""}@${merchant.adminEmail.split("@")[1]}`,
        statusId: merchant.status === "SUSPENDED" ? 1 : 2,
        channels: pickN(["IN_APP", "IN_STORE", "DELIVERY", "REMOTE", "OFFLINE"], randInt(2, 4)),
        isPhysical: true,
        inventoryMigrated: merchant.model === "EXPRESS",
        minimumDownPayment: 1000, // $10.00
        minimumFinanceableAmount: 2500, // $25.00
        address: {
          name: veAddress(),
          long: f.location.longitude(),
          lat: f.location.latitude(),
          location: veCity(),
          shipmentsEnabled: true,
        },
        createdAt: merchant.createdAt,
        scenarioTags: [],
        invoiceRegistrationFailing: false,
        orderCreateConnectionError: false,
      };
      db.stores.set(store.uuid, store);
    }
  }

  // ── 3. Empleados ────────────────────────────────────────────────
  let empCounter = 1;
  for (const store of db.stores.values()) {
    const empCount = randInt(2, 4);
    const roles: ("ADMIN" | "MANAGER" | "CASHIER")[] = ["ADMIN"];
    // Asegurar al menos un MANAGER si hay >2 empleados
    if (empCount >= 3) roles.push("MANAGER");
    for (let i = 1; i < empCount; i++) {
      roles.push(i === 1 && empCount >= 3 ? "MANAGER" : pick(["CASHIER", "MANAGER", "CASHIER"]));
    }

    for (const role of roles) {
      const fullName = veFullName();
      const employee: Employee = {
        id: `emp_${empCounter.toString().padStart(4, "0")}`,
        storeUuid: store.uuid,
        merchantId: store.merchantId,
        name: fullName,
        email: veEmail(fullName),
        role,
        onboardingStatus: "FINISHED",
        phoneRegistered: f.datatype.boolean({ probability: 0.8 }),
        phoneNumber: vePhone(),
        mustChangePassword: false,
        securityCodeSet: role === "ADMIN" || f.datatype.boolean({ probability: 0.7 }),
        lastLoginAt: f.datatype.boolean({ probability: 0.85 })
          ? isoDaysAgo(randInt(0, 14))
          : null,
        createdAt: store.createdAt,
        scenarioTags: [],
        otpNeverArrives: false,
      };
      empCounter++;
      db.employees.set(employee.id, employee);
    }
  }

  // ── 4. POS (cajas) ──────────────────────────────────────────────
  let posCounter = 1;
  for (const store of db.stores.values()) {
    const posCount = randInt(1, 2);
    for (let i = 0; i < posCount; i++) {
      const posUuid = uuid();
      const pos: POS = {
        posUuid,
        name: `POS ${posCounter} - ${store.name.slice(0, 20)}`,
        storeUuid: store.uuid,
        merchantId: store.merchantId,
        qrLinked: f.datatype.boolean({ probability: 0.85 }),
        qrCode: null,
        lastOrderAt: f.datatype.boolean({ probability: 0.8 })
          ? isoDaysAgo(randInt(0, 7))
          : null,
        scenarioTags: [],
      };
      if (pos.qrLinked) {
        pos.qrCode = {
          activationCode: f.string.numeric({ length: 6 }),
          status: "LINKED",
        };
      }
      posCounter++;
      db.pos.push(pos);
    }
  }

  // ── 5. Payment methods por store ────────────────────────────────
  let pmCounter = 1;
  for (const store of db.stores.values()) {
    const methods: ("PAGO_MOVIL" | "TRANSFERENCIA" | "EFECTIVO" | "TARJETA")[] =
      pickN(
        ["PAGO_MOVIL", "TRANSFERENCIA", "EFECTIVO", "TARJETA"],
        randInt(2, 4),
      );
    for (const name of methods) {
      const pm: PaymentMethod = {
        id: pmCounter++,
        storeUuid: store.uuid,
        name,
        type: name === "EFECTIVO" ? "CASH" : name === "TARJETA" ? "CARD" : "BANK",
        bankName: name === "PAGO_MOVIL" || name === "TRANSFERENCIA" ? veBank() : null,
        bankHolder: name === "PAGO_MOVIL" || name === "TRANSFERENCIA" ? store.name : null,
        account:
          name === "TRANSFERENCIA"
            ? `0${f.string.numeric({ length: 11 })}`
            : null,
        accountType: name === "TRANSFERENCIA" ? "CORRIENTE" : null,
        phoneNumber: name === "PAGO_MOVIL" ? vePhone() : null,
        currencyId: name === "EFECTIVO" || name === "TARJETA" ? 1 : 2,
        currency: {
          id: name === "EFECTIVO" || name === "TARJETA" ? 1 : 2,
          name: name === "EFECTIVO" || name === "TARJETA" ? "USD" : "VES",
        },
        category: "IN_STORE",
        fees: [],
      };
      db.paymentMethods.push(pm);
    }
  }

  // ── 6. Productos por store ──────────────────────────────────────
  let prodUuidCounter = 0;
  for (const store of db.stores.values()) {
    const merchant = db.merchants.get(store.merchantId)!;
    const categoryData = PRODUCT_CATEGORIES[merchant.categoryId];
    if (!categoryData) continue;
    const productCount = randInt(5, 12);
    for (let i = 0; i < productCount; i++) {
      const template = pick(categoryData.products);
      const price = money(template.priceRange[0], template.priceRange[1]);
      prodUuidCounter++;
      const product: Product = {
        uuid: uuid(),
        storeUuid: store.uuid,
        sku: `SKU-${merchant.id}-${prodUuidCounter.toString().padStart(4, "0")}`,
        name: template.name,
        price,
        stock: randInt(0, 50),
        categoryId: merchant.categoryId,
        categoryName: categoryData.name,
        status: f.datatype.boolean({ probability: 0.9 }) ? "ACTIVE" : "PAUSED",
        type: "PHYSICAL",
        imgUrl: "",
      };
      db.products.push(product);
    }
  }

  // ── 7. Órdenes con cuotas y pagos coherentes ────────────────────
  // Distribuir ~100 órdenes en los últimos 90 días
  const totalOrders = 100;
  const allStoreUuids = [...db.stores.keys()];

  for (let i = 0; i < totalOrders; i++) {
    const storeUuid = pick(allStoreUuids);
    const store = db.stores.get(storeUuid)!;
    const merchant = db.merchants.get(store.merchantId)!;
    if (!merchant) continue;

    const daysAgo = randInt(0, 89);
    const createdAt = isoDaysAgo(daysAgo);
    const orderNumber = generateOrderNumber();

    // Montos coherentes
    const totalAmount = money(30, 800);
    const downPaymentPct = weighted([
      [0.25, 3],
      [0.3, 2],
      [0.4, 2],
      [0.5, 2],
    ]);
    const downPaymentAmount = Math.round(totalAmount * downPaymentPct);
    const financedAmount = totalAmount - downPaymentAmount;

    // Estado de la orden
    const statusRoll = f.number.float({ min: 0, max: 1 });
    let status: Order["status"];
    let statusId: number;
    if (daysAgo < 3 && statusRoll < 0.15) {
      status = "PENDING";
      statusId = 7;
    } else if (statusRoll < 0.2) {
      status = "IN_PROGRESS";
      statusId = 1;
    } else if (statusRoll < 0.25) {
      status = "OPEN";
      statusId = 3;
    } else if (statusRoll < 0.3) {
      status = "CANCELLED";
      statusId = 4;
    } else {
      status = "CLOSED";
      statusId = 2;
    }

    // Canal
    const channel = weighted<Order["channel"]>([
      ["IN_STORE", 4],
      ["REMOTE", 2],
      ["OFFLINE", 1],
      ["IN_APP", 2],
    ]);

    // Productos (1-4 items que sumen aprox el total)
    const products: Order["products"] = [];
    let remaining = totalAmount;
    const itemCount = randInt(1, 4);
    for (let p = 0; p < itemCount; p++) {
      const isLast = p === itemCount - 1;
      const productPrice = isLast ? remaining : Math.min(remaining, money(15, Math.max(20, remaining / 100)));
      if (productPrice <= 0) break;
      remaining -= productPrice;
      products.push({
        id: uuid(),
        name: pick(PRODUCT_CATEGORIES[merchant.categoryId]?.products ?? [{ name: "Producto", priceRange: [10, 50] }]).name,
        quantity: 1,
        price: productPrice,
        priceAfterDiscount: null,
      });
    }

    // POS
    const storePOS = db.pos.filter((p) => p.storeUuid === storeUuid);
    const orderPOS = storePOS.length > 0 ? pick(storePOS) : null;

    // Comprador
    const buyerName = veFullName();
    const buyer: Order["buyer"] = {
      fullName: buyerName,
      identificationNumber: veCedula(),
      phoneNumber: vePhone(),
      email: veEmail(buyerName),
    };

    // Delivery
    const deliveryType = channel === "REMOTE" || channel === "IN_APP"
      ? pick(["SHIPMENT", "AGREE_WITH_STORE", "IN_STORE"] as const)
      : "IN_STORE";
    const deliveryStatus = status === "CANCELLED" ? "CANCELLED" : deliveryType === "IN_STORE" ? "DELIVERED" : pick(["TO_DELIVER", "DELIVERED", "PENDING"] as const);
    const shipmentStatus = deliveryType === "SHIPMENT" && status !== "CANCELLED"
      ? pick(["DELIVERED", "IN_TRANSIT", "WAITING_CONFIRMATION", "COMPLETED"] as const)
      : null;

    // Invoice
    const invoiceRegistered = status === "CLOSED" && f.datatype.boolean({ probability: 0.85 });
    const invoice: Order["invoice"] = {
      registered: invoiceRegistered,
      number: invoiceRegistered ? `F-${f.string.numeric({ length: 6 })}` : null,
      registeredAt: invoiceRegistered ? isoDaysAgo(Math.max(0, daysAgo - 1)) : null,
    };

    // Cancellation data
    const cancellationData = status === "CANCELLED"
      ? {
          cancelledBy: pick(["ADMIN", "MANAGER"]),
          reason: pick(CANCELLATION_REASONS).reason,
          cancelledAt: isoDaysAgo(Math.max(0, daysAgo - 1)),
        }
      : null;

    const order: Order = {
      orderNumber,
      uuid: uuid(),
      storeUuid,
      merchantId: store.merchantId,
      status,
      statusId,
      channel,
      deliveryType: deliveryType as string,
      deliveryStatus: deliveryStatus as string,
      shipmentStatus,
      totalAmount,
      downPaymentAmount,
      financedAmount,
      currency: "USD",
      products,
      buyer,
      pos: orderPOS ? { name: orderPOS.name, uuid: orderPOS.posUuid } : null,
      invoice,
      cancellationData,
      createdAt,
      scenarioTags: [],
    };

    db.orders.set(orderNumber, order);

    // ── Cuotas y pagos de la orden ────────────────────────────────
    if (status !== "CANCELLED" && status !== "PENDING") {
      const planCount = weighted([
        [3, 3],
        [6, 4],
        [12, 2],
      ]);
      const installmentBase = Math.round(financedAmount / planCount);
      const installmentDates: string[] = [];
      for (let n = 0; n < planCount; n++) {
        installmentDates.push(isoDaysAgo(daysAgo - 30 * (n + 1)));
      }

      for (let n = 0; n < planCount; n++) {
        const installmentNumber = n + 1;
        const isPast = daysAgo > 30 * installmentNumber;
        const instStatus: OrderInstallment["status"] = isPast
          ? f.datatype.boolean({ probability: 0.92 })
            ? "DONE"
            : "DELAYED"
          : installmentNumber === 1 && daysAgo > 0
            ? "DONE"
            : "SCHEDULED";

        const payments: OrderInstallment["payments"] = [];

        // Pago inicial (downPayment) va en la cuota 1
        if (installmentNumber === 1 && (instStatus === "DONE" || f.datatype.boolean({ probability: 0.7 }))) {
          const paymentMethod = pick(["PAGO_MOVIL", "TRANSFERENCIA", "EFECTIVO", "TARJETA"] as const);
          payments.push({
            paymentId: `pmt_${f.string.numeric({ length: 6 })}`,
            assignedAmount: installmentBase + downPaymentAmount,
            paymentMethod: { name: paymentMethod },
            paymentStatus: "VERIFIED",
            referenceNumber: paymentMethod === "PAGO_MOVIL" || paymentMethod === "TRANSFERENCIA"
              ? veBankReference()
              : null,
            amountVES: paymentMethod === "PAGO_MOVIL" || paymentMethod === "TRANSFERENCIA"
              ? toVES(installmentBase + downPaymentAmount)
              : null,
            paymentValidationDate: isoDaysAgo(Math.max(0, daysAgo - 1)),
            createdAt,
          });
        }

        // Pagos de cuotas posteriores
        if (installmentNumber > 1 && instStatus === "DONE") {
          const paymentMethod = pick(["PAGO_MOVIL", "TRANSFERENCIA", "EFECTIVO"] as const);
          payments.push({
            paymentId: `pmt_${f.string.numeric({ length: 6 })}`,
            assignedAmount: installmentBase,
            paymentMethod: { name: paymentMethod },
            paymentStatus: "VERIFIED",
            referenceNumber: paymentMethod !== "EFECTIVO" ? veBankReference() : null,
            amountVES: paymentMethod !== "EFECTIVO" ? toVES(installmentBase) : null,
            paymentValidationDate: installmentDates[n],
            createdAt: installmentDates[n],
          });
        }

        const installment: OrderInstallment = {
          id: `ins_${f.string.numeric({ length: 6 })}`,
          orderUuid: order.uuid,
          installmentNumber,
          amount: installmentNumber === 1 ? installmentBase + downPaymentAmount : installmentBase,
          dueDate: installmentDates[n],
          status: instStatus,
          payments,
        };
        db.installments.push(installment);
      }
    }
  }

  // ── 8. Conciliaciones diarias (derivadas de órdenes) ────────────
  // Para los últimos 30 días, por store
  for (const store of db.stores.values()) {
    for (let d = 0; d < 30; d++) {
      const dayKey = daysAgoKey(d);
      const dayOrders = [...db.orders.values()].filter(
        (o) => o.storeUuid === store.uuid && dateKey(o.createdAt) === dayKey,
      );
      if (dayOrders.length === 0) continue;

      const storePOS = db.pos.filter((p) => p.storeUuid === store.uuid);
      const posConciliations = storePOS.map((pos) => {
        const posOrders = dayOrders.filter((o) => o.pos?.uuid === pos.posUuid);
        return {
          pos: { name: pos.name, uuid: pos.posUuid },
          ordersCount: posOrders.length,
          totalChargedAmount: posOrders.reduce((s, o) => s + o.downPaymentAmount, 0),
          totalFinancedAmount: posOrders.reduce((s, o) => s + o.financedAmount, 0),
        };
      });

      // Incluir órdenes sin POS asignado
      const noPosOrders = dayOrders.filter((o) => !o.pos);
      if (noPosOrders.length > 0) {
        posConciliations.push({
          pos: { name: "Sin POS", uuid: "n/a" },
          ordersCount: noPosOrders.length,
          totalChargedAmount: noPosOrders.reduce((s, o) => s + o.downPaymentAmount, 0),
          totalFinancedAmount: noPosOrders.reduce((s, o) => s + o.financedAmount, 0),
        });
      }

      const conc: DailyConciliation = {
        id: db.dailyConciliations.length + 1,
        storeUuid: store.uuid,
        createdAt: isoDaysAgo(d),
        date: dayKey,
        ordersCount: dayOrders.length,
        totalChargedAmount: dayOrders.reduce((s, o) => s + o.downPaymentAmount, 0),
        totalFinancedAmount: dayOrders.reduce((s, o) => s + o.financedAmount, 0),
        posConciliations,
      };
      db.dailyConciliations.push(conc);
    }
  }

  // ── 9. Reportes mensuales + payouts + facturas (3 periodos) ─────
  for (const merchant of db.merchants.values()) {
    if (merchant.status === "SUSPENDED") continue;

    for (let p = 0; p < 3; p++) {
      const periodEnd = isoDaysAgo(p * 30);
      const periodStart = isoDaysAgo(p * 30 + 30);
      const periodLabel = monthLabel(p);

      // Órdenes del merchant en ese periodo
      const periodOrders = [...db.orders.values()].filter((o) => {
        if (o.merchantId !== merchant.id) return false;
        const created = new Date(o.createdAt).getTime();
        return created >= new Date(periodStart).getTime() && created < new Date(periodEnd).getTime();
      });

      const grossAmount = periodOrders.reduce((s, o) => s + o.totalAmount, 0);
      const techServicesAmount = Math.round(grossAmount * 0.03); // 3% tech services
      const ivaAmount = Math.round(techServicesAmount * 0.16); // 16% IVA
      const isrlRetainedAmount = Math.round(grossAmount * 0.02); // 2% ISRL
      const serviceFeeTotal = techServicesAmount + ivaAmount;
      const adjustments = f.number.int({ min: -500, max: 500 }) * 100; // ±$5 aleatorio
      const netAmount = grossAmount - serviceFeeTotal - isrlRetainedAmount + adjustments;

      const expectedAmount = periodOrders.reduce((s, o) => s + o.financedAmount, 0);
      const receivedAmount = Math.round(expectedAmount * f.number.float({ min: 0.85, max: 0.98 }));
      const advancedAmount = Math.round(expectedAmount * f.number.float({ min: 0.01, max: 0.05 }));
      const missed = expectedAmount - receivedAmount - advancedAmount;
      const paymentErrorsAmount = f.number.int({ min: 0, max: 30 }) * 100;
      const periodAdjustmentsAmount = adjustments;

      // Timeline
      const isCurrentPeriod = p === 0;
      const timeline: MonthlyReport["paymentTimeline"] = [
        {
          stepKey: "reportSent",
          status: "completed",
          date: periodEnd,
        },
        {
          stepKey: "calculationConfirmed",
          status: isCurrentPeriod ? "in-progress" : "completed",
          date: isCurrentPeriod ? null : isoDaysAgo(p * 30 - 2),
        },
        {
          stepKey: "invoiceGenerated",
          status: isCurrentPeriod ? "pending" : "completed",
          date: isCurrentPeriod ? null : isoDaysAgo(p * 30 - 5),
        },
        {
          stepKey: "bankDeposit",
          status: isCurrentPeriod ? "pending" : "completed",
          date: isCurrentPeriod ? null : isoDaysAgo(p * 30 - 7),
        },
      ];

      const report: MonthlyReport = {
        merchantId: merchant.id,
        period: { from: periodStart, to: periodEnd },
        periodLabel,
        compensation: {
          totalAmount: netAmount,
          shouldMerchantPay: netAmount < 0,
        },
        paymentTimeline: timeline,
        missedInstallments: {
          amount: missed,
          expectedAmount,
          receivedAmount,
          advancedAmount,
        },
        serviceFee: {
          amount: serviceFeeTotal,
          techServicesAmount,
          ivaAmount,
          isrlRetainedAmount,
        },
        errorsAndAdjustments: {
          amount: paymentErrorsAmount + periodAdjustmentsAmount,
          paymentErrorsAmount,
          periodAdjustmentsAmount,
        },
      };
      db.monthlyReports.push(report);

      // Payout (solo si el periodo ya terminó = p > 0, o p === 0 pero ya pasaron 7 días)
      if (p > 0) {
        const payoutStatus: Payout["status"] = f.datatype.boolean({ probability: 0.85 })
          ? "SENT"
          : pick(["PENDING", "FAILED"] as const);
        const payout: Payout = {
          id: `pyt_${merchant.id}_${periodLabel}`,
          merchantId: merchant.id,
          periodFrom: periodStart,
          periodTo: periodEnd,
          periodLabel,
          grossAmount,
          serviceFee: serviceFeeTotal,
          retentions: isrlRetainedAmount,
          adjustments,
          netAmount,
          status: payoutStatus,
          sentAt: payoutStatus === "SENT" ? isoDaysAgo(p * 30 - 7) : null,
          bankReference: payoutStatus === "SENT" ? veBankReference() : null,
          bankAccountLast4: f.string.numeric({ length: 4 }),
          scenarioTags: [],
        };
        db.payouts.push(payout);
      }

      // Invoice
      const invoiceStatus: Invoice["status"] = isCurrentPeriod
        ? "ISSUED"
        : f.datatype.boolean({ probability: 0.8 })
          ? "SENT"
          : "NOT_SENT";
      const invoice: Invoice = {
        id: `inv_${merchant.id}_${periodLabel}`,
        merchantId: merchant.id,
        period: { from: periodStart, to: periodEnd },
        periodLabel,
        number: `F-${merchant.id}-${periodLabel.replace("-", "")}`,
        amount: techServicesAmount,
        iva: ivaAmount,
        isrlRetained: isrlRetainedAmount,
        status: invoiceStatus,
        sentToEmail: invoiceStatus === "SENT" ? merchant.adminEmail : null,
        sentAt: invoiceStatus === "SENT" ? isoDaysAgo(p * 30 - 5) : null,
        pdfUrl: `https://merchant-mock.local/invoices/${merchant.id}/${periodLabel}.pdf`,
        scenarioTags: [],
      };
      db.invoices.push(invoice);
    }
  }

  // ── 10. Promociones ─────────────────────────────────────────────
  const promotions: Promotion[] = [
    {
      id: "promo_001",
      title: "Descuento en línea principal",
      description: "10% de descuento en productos de línea principal",
      status: "ACTIVE",
      scheduleState: "ACTIVE",
      startsAt: isoDaysAgo(20),
      endsAt: isoDaysFromNow(40),
      enrollmentStatus: "JOINED",
      mechanics: [{ kind: "DISCOUNT", label: "10% off" }],
      conditionGroups: [{
        id: "cg_001",
        name: "Elegibilidad general",
        conditions: [{ kind: "USER_LEVEL", label: "Bronze+" }],
      }],
      links: {
        infoDocumentUrl: "https://merchant-mock.local/promos/001/info",
        termsAndConditionsUrl: "https://merchant-mock.local/promos/001/tc",
      },
    },
    {
      id: "promo_002",
      title: "Cuotas extra en electrónica",
      description: "Plan de 15 cuotas en productos de electrónica",
      status: "ACTIVE",
      scheduleState: "ACTIVE",
      startsAt: isoDaysAgo(15),
      endsAt: isoDaysFromNow(45),
      enrollmentStatus: "AVAILABLE",
      mechanics: [{ kind: "EXTRA_INSTALLMENT_PLAN", label: "15 cuotas" }],
      conditionGroups: [{
        id: "cg_002",
        name: "Comercios incluidos",
        conditions: [{ kind: "INCLUDED_MERCHANTS", label: "Solo comercios seleccionados" }],
      }],
      links: {
        infoDocumentUrl: "https://merchant-mock.local/promos/002/info",
        termsAndConditionsUrl: "https://merchant-mock.local/promos/002/tc",
      },
    },
    {
      id: "promo_003",
      title: "Inicial reducida en hogar",
      description: "Solo 15% de inicial en muebles del hogar",
      status: "ACTIVE",
      scheduleState: "NOT_STARTED",
      startsAt: isoDaysFromNow(10),
      endsAt: isoDaysFromNow(70),
      enrollmentStatus: "AVAILABLE",
      mechanics: [{ kind: "DP_REDUCTION", label: "15% inicial" }],
      conditionGroups: [{
        id: "cg_003",
        name: "Categoría hogar",
        conditions: [{ kind: "USER_LEVEL", label: "Todos los niveles" }],
      }],
      links: {
        infoDocumentUrl: "https://merchant-mock.local/promos/003/info",
        termsAndConditionsUrl: "https://merchant-mock.local/promos/003/tc",
      },
    },
    {
      id: "promo_004",
      title: "Black Friday Cashea",
      description: "Descuentos especiales por Black Friday",
      status: "INACTIVE",
      scheduleState: "NOT_STARTED",
      startsAt: isoDaysFromNow(60),
      endsAt: isoDaysFromNow(90),
      enrollmentStatus: "NONE",
      mechanics: [{ kind: "DISCOUNT", label: "Hasta 30% off" }],
      conditionGroups: [{
        id: "cg_004",
        name: "Todos los comercios",
        conditions: [{ kind: "USER_LEVEL", label: "Todos los niveles" }],
      }],
      links: {
        infoDocumentUrl: null,
        termsAndConditionsUrl: null,
      },
    },
  ];
  db.promotions.push(...promotions);

  // ── 11. Onboardings ─────────────────────────────────────────────
  const onboarding1: Onboarding = {
    onboardingId: "onb_0001",
    merchantId: 5, // Sport Plus (suspended)
    step: "LEGAL_DOCUMENTS",
    status: "IN_PROGRESS",
    failedRules: ["contract_not_signed", "bank_data_missing"],
    legalDocuments: [
      { name: "Contrato de servicios Cashea", status: "PENDING" },
      { name: "Contrato de cesión de facturas", status: "PENDING" },
    ],
    bankAccountVerified: false,
    readyToGo: false,
    plan: null,
    channelsSelected: ["IN_STORE"],
    createdAt: isoDaysAgo(15),
    scenarioTags: [],
  };
  db.onboardings.set(onboarding1.onboardingId, onboarding1);

  const onboarding2: Onboarding = {
    onboardingId: "onb_0002",
    merchantId: 3, // TechStore
    step: "COMPLETED",
    status: "APPROVED",
    failedRules: [],
    legalDocuments: [
      { name: "Contrato de servicios Cashea", status: "SIGNED" },
      { name: "Contrato de cesión de facturas", status: "SIGNED" },
    ],
    bankAccountVerified: true,
    readyToGo: true,
    plan: "EXPRESS",
    channelsSelected: ["IN_STORE", "IN_APP", "REMOTE"],
    createdAt: isoDaysAgo(90),
    scenarioTags: [],
  };
  db.onboardings.set(onboarding2.onboardingId, onboarding2);

  // ── 12. Reports hub y movements ─────────────────────────────────
  const reports: Report[] = [
    {
      id: "rep_001",
      title: "Reporte de ventas mensual",
      description: "Resumen completo de ventas del último mes",
      longDescription: "Incluye ventas por canal, productos más vendidos y métricas de desempeño.",
      url: "https://merchant-mock.local/reports/monthly-sales",
    },
    {
      id: "rep_002",
      title: "Reporte de conciliación diaria",
      description: "Detalle de conciliaciones diarias por tienda",
      longDescription: "Desglose por POS, método de pago y estado de cuotas.",
      url: "https://merchant-mock.local/reports/daily-conciliation",
    },
    {
      id: "rep_003",
      title: "Reporte de cuotas pendientes",
      description: "Cuotas vencidas y próximas a vencer",
      longDescription: "Seguimiento de morosidad y estimación de ingresos futuros.",
      url: "https://merchant-mock.local/reports/pending-installments",
    },
  ];
  db.reports.push(...reports);

  for (let i = 0; i < 10; i++) {
    db.movements.push({
      id: `mov_${(i + 1).toString().padStart(4, "0")}`,
      title: pick([
        "Pago de cuota recibido",
        "Nueva orden creada",
        "Orden cancelada",
        "Transferencia enviada",
        "Factura generada",
        "Conciliación completada",
      ]),
      description: null,
      longDescription: null,
      url: "https://merchant-mock.local/movements",
      date: isoDaysAgo(randInt(0, 30)),
    });
  }

  // ── Aplicar escenarios (mutaciones que crean anomalías) ─────────
  applyScenarios(db);

  // ── Instalar el DB ──────────────────────────────────────────────
  setDB(db);

  // ── Log de startup ──────────────────────────────────────────────
  const scenarioCount = countScenarioTags(db);
  console.log("🌱 Merchant mock seed completado:");
  console.log(`   ${db.merchants.size} merchants`);
  console.log(`   ${db.stores.size} stores`);
  console.log(`   ${db.employees.size} employees`);
  console.log(`   ${db.orders.size} orders`);
  console.log(`   ${db.installments.length} installments`);
  console.log(`   ${db.dailyConciliations.length} daily conciliations`);
  console.log(`   ${db.monthlyReports.length} monthly reports`);
  console.log(`   ${db.payouts.length} payouts`);
  console.log(`   ${db.invoices.length} invoices`);
  console.log(`   ${db.promotions.length} promotions`);
  console.log(`   ${db.pos.length} POS`);
  console.log(`   ${db.paymentMethods.length} payment methods`);
  console.log(`   ${db.products.length} products`);
  console.log(`   ${db.onboardings.size} onboardings`);
  console.log(`   ${scenarioCount} entidades con scenario tags`);
}

export function reseed(): void {
  runSeed();
}

// ── Helpers privados ───────────────────────────────────────────────

function generateOrderNumber(): string {
  // Generar número de 9 dígitos determinista
  orderNumCounter++;
  const base = 197000000 + orderNumCounter;
  return base.toString();
}

function monthLabel(monthsAgo: number): string {
  const d = new Date(Date.now() - monthsAgo * 30 * 86_400_000);
  return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, "0")}`;
}

function countScenarioTags(db: Database): number {
  let count = 0;
  for (const m of db.merchants.values()) count += m.scenarioTags.length;
  for (const s of db.stores.values()) count += s.scenarioTags.length;
  for (const e of db.employees.values()) count += e.scenarioTags.length;
  for (const o of db.orders.values()) count += o.scenarioTags.length;
  for (const p of db.payouts) count += p.scenarioTags.length;
  for (const i of db.invoices) count += i.scenarioTags.length;
  for (const pos of db.pos) count += pos.scenarioTags.length;
  for (const o of db.onboardings.values()) count += o.scenarioTags.length;
  return count;
}
