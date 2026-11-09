const express = require('express');

const {
    buscarPorCpf
} = require('../controllers/responsavelController');

const router = express.Router();
router.use(require('../middlewares/authMiddleware'));

router.get('/:cpf', buscarPorCpf);

module.exports = router;