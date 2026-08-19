import { Router, type IRouter } from "express";
import healthRouter from "./health";
import productionsRouter from "./productions";

const router: IRouter = Router();

router.use(healthRouter);
router.use(productionsRouter);

export default router;
