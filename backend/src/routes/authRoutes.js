const express = require('express');
const { rateLimit } = require('express-rate-limit');
const { login, logout } = require('../controllers/authController');
const autenticar = require('../middlewares/authMiddleware');
const router = express.Router();
router.post('/login', rateLimit({
    windowMs: 15 * 60 * 1000, limit: 10, standardHeaders: 'draft-8', legacyHeaders: false,
    message: { erro: 'Muitas tentativas. Tente novamente em 15 minutos.' }
}), login);
router.post('/logout', logout);
router.get('/me', autenticar, (req, res) => res.json({ administrador: req.administrador }));
module.exports = router;
