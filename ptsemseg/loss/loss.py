import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import cv2
from torch.autograd import Variable as V
import keras.backend as K

########################################################################################################################
###
########################################################################################################################
def cross_entropy2d(input, target, weight=None, size_average=True):
    n, c, h, w = input.size()
    nt, ht, wt = target.size()

    if h != ht and w != wt:  # upsample labels
        input = F.interpolate(input, size=(ht, wt), mode="bilinear", align_corners=True)

    input = input.transpose(1, 2).transpose(2, 3).contiguous().view(-1, c)
    target = target.view(-1)
    
    loss = F.cross_entropy(
              input, target, weight=weight, size_average=size_average, ignore_index=250, reduction='mean')

    return loss



########################################################################################################################
###
########################################################################################################################
def multi_scale_cross_entropy2d(input, target, loss_th, weight=None, size_average=True, scale_weight=[1.0, 0.4]):
    if not isinstance(input, tuple):
        return cross_entropy2d(input=input, target=target, weight=weight, size_average=size_average)

    K = input[0].size()[2] * input[0].size()[3] // 128
    loss = 0.0

    for i, inp in enumerate(input):
        loss = loss + scale_weight[i] * bootstrapped_cross_entropy2d(
            input=inp, target=target, min_K=K, loss_th=loss_th, weight=weight, size_average=size_average
        )

    return loss


########################################################################################################################
###
########################################################################################################################
def bootstrapped_cross_entropy2d(input, target, min_K, loss_th, weight=None, size_average=True, train_val = 0, dev = None):
    n, c, h, w = input.size()
    nt, ht, wt = target.size()
    batch_size = input.size()[0]
    
    if h != ht and w != wt:  # upsample labels
        input = F.interpolate(input, size=(ht, wt), mode="bilinear", align_corners=True)
    
    thresh = loss_th
    
    def _bootstrap_xentropy_single(input, target, K, thresh, weight=None, size_average=True, train_validation = 0):

        n, c, h, w = input.size()
        input = input.transpose(1, 2).transpose(2, 3).contiguous().view(-1, c)
        target = target.view(-1)
        loss = F.cross_entropy(
            input, target, weight=weight, reduce=False, size_average=False, ignore_index=250
        )

        # for i,item in enumerate(target):
        #     if item == 1:
        #         indices.append(i)
        if train_validation == 0:
            sorted_loss, _ = torch.sort(loss, descending=True)

            if sorted_loss[K] > thresh:
                loss = sorted_loss[sorted_loss > thresh]
            else:
                loss = sorted_loss[:K]

        reduced_topk_loss = torch.mean(loss)

        return reduced_topk_loss
    #end

    loss = 0.0
    # Bootstrap from each image not entire batch
    for i in range(batch_size):
        loss += _bootstrap_xentropy_single(
            input=torch.unsqueeze(input[i], 0),
            target=torch.unsqueeze(target[i], 0),
            K=min_K,
            thresh=thresh,
            weight=weight,
            size_average=size_average,
            train_validation = train_val,
        )
    # print(loss / float(batch_size))
    return loss / float(batch_size)


def dice_ce_loss(input, target, min_K, loss_th, weight=None, size_average=True, train_val = 0, dev = None ):
    ce_loss = cross_entropy2d(input, target)
    eps=1e-7
    true_1_hot = torch.eye(3)[target.squeeze(1)]
    true_1_hot = true_1_hot.permute(0, 3, 1, 2).float()
    probas = F.softmax(input, dim=1)
    true_1_hot = true_1_hot.type(input.type())
    dims = (0,) + tuple(range(2, target.ndimension()))
    intersection = torch.sum(probas * true_1_hot, dims)
    cardinality = torch.sum(probas + true_1_hot, dims)
    dice_loss = (2. * intersection / (cardinality + eps)).mean()
    return (1 - dice_loss) + ce_loss


def CrossEntropyLoss2d_Weighted(input, target, min_K, loss_th, weight=None, size_average=True, train_val = 0, dev = None ):
    class_weights = torch.ones(4)
    class_weights[0] = 2
    class_weights[1] = 0.09
    class_weights[2] = 2
    class_weights[3] = 45
    class_weights = class_weights.to(dev)
    NLLloss = torch.nn.NLLLoss2d(class_weights)
    return NLLloss(torch.nn.functional.log_softmax(input, dim=1), target)