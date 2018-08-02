# coding=utf-8
import os

import cv2
import numpy as np
from scipy.special import gamma
import svmutil
from svmutil import gen_svm_nodearray
from ctypes import c_double

from utilities import root_path


class BRISQUE(object):
    def __init__(self):
        self._model = svmutil.svm_load_model(root_path('allmodel'))

    @staticmethod
    def preprocess_image(img):
        if isinstance(img, str):
            if os.path.exists(img):
                return cv2.imread(img, 0).astype(np.float32)
            else:
                raise FileNotFoundError('The image is not found on your '
                                        'system.')
        elif isinstance(img, np.ndarray):
            if len(img.shape) == 2:
                image = img
            elif len(img.shape) == 3:
                image = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                raise ValueError('The image shape is not correct.')

            return image.astype(np.float32)
        else:
            raise ValueError('You can only pass image to the constructor.')

    @staticmethod
    def _estimate_ggd_param(vec):
        gam = np.arange(0.2, 10 + 0.001, 0.001)
        r_gam = (gamma(1.0 / gam) * gamma(3.0 / gam) / (gamma(2.0 / gam) ** 2))

        sigma_sq = np.mean(vec ** 2)
        sigma = np.sqrt(sigma_sq)
        E = np.mean(np.abs(vec))
        rho = sigma_sq / E ** 2

        differences = abs(rho - r_gam)
        array_position = np.argmin(differences)
        gamparam = gam[array_position]

        return gamparam, sigma

    @staticmethod
    def _estimate_aggd_param(vec):
        gam = np.arange(0.2, 10 + 0.001, 0.001)
        r_gam = ((gamma(2.0 / gam)) ** 2) / (
                    gamma(1.0 / gam) * gamma(3.0 / gam))

        left_std = np.sqrt(np.mean((vec[vec < 0]) ** 2))
        right_std = np.sqrt(np.mean((vec[vec > 0]) ** 2))
        gamma_hat = left_std / right_std
        rhat = (np.mean(np.abs(vec))) ** 2 / np.mean((vec) ** 2)
        rhat_norm = (rhat * (gamma_hat ** 3 + 1) * (gamma_hat + 1)) / (
                (gamma_hat ** 2 + 1) ** 2)

        differences = (r_gam - rhat_norm) ** 2
        array_position = np.argmin(differences)
        alpha = gam[array_position]

        return alpha, left_std, right_std

    def get_feature(self, img):
        """Assuming that the image is already in grayscale."""
        image = self.preprocess_image(img)

        scale_num = 2
        feat = np.array([])

        for itr_scale in range(scale_num):
            scale = 1. / (itr_scale + 1)
            imdist = cv2.resize(
                image,
                (int(scale * image.shape[1]),
                 int(scale * image.shape[0]))
            )

            mu = cv2.GaussianBlur(
                imdist, (7, 7), 7 / 6, borderType=cv2.BORDER_CONSTANT)
            mu_sq = mu * mu
            sigma = cv2.GaussianBlur(
                imdist * imdist, (7, 7), 7 / 6, borderType=cv2.BORDER_CONSTANT)
            sigma = np.sqrt(abs((sigma - mu_sq)))
            structdis = (imdist - mu) / (sigma + 1)

            alpha, overallstd = self._estimate_ggd_param(structdis)
            feat = np.append(feat, [alpha, overallstd ** 2])

            shifts = [[0, 1], [1, 0], [1, 1], [-1, 1]]
            for shift in shifts:
                M = np.float32([[1, 0, shift[1]], [0, 1, shift[0]]])
                shifted_structdis = cv2.warpAffine(np.float32(structdis), M, (
                    structdis.shape[1], structdis.shape[0]))
                pair = structdis * shifted_structdis
                alpha, left_std, right_std = self._estimate_aggd_param(pair)

                const = np.sqrt(gamma(1 / alpha)) / np.sqrt(gamma(3 / alpha))
                mean_param = (right_std - left_std) * (
                        gamma(2 / alpha) / gamma(1 / alpha)) * const
                feat = np.append(
                    feat, [alpha, mean_param, left_std ** 2, right_std ** 2])

        return feat

    def get_score(self, img):
        feature = self.get_feature(img)

        x, idx = gen_svm_nodearray(
            feature[1:].tolist(),
            isKernel=(self._model.param.kernel_type == 'PRECOMPUTED')
        )
        nr_classifier = 1
        prob_estimates = (c_double * nr_classifier)()

        return svmutil.libsvm.svm_predict_probability(
            self._model, x, prob_estimates)