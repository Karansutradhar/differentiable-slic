import os
import torch
import torch.optim as optim
import numpy as np
from tqdm import tqdm

# import cv2
# import matplotlib.pyplot as plt

from pytorch_ssn.model.SSN import SSN, crop_like, superpixel_flow
# import pytorch_ssn.IO as IO
from pytorch_ssn.connectivity import enforce_connectivity
from pytorch_ssn.model.util import get_spixel_image
from pytorch_ssn.RAFT.core.raft import RAFT
from pytorch_ssn.model.ResUnet import ResUnet

os.environ['CUDA_VISIBLE_DEVICES']='0'
device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
print(device)

try:
    from torch.cuda.amp import GradScaler
except:
    # dummy GradScaler for PyTorch < 1.6
    class GradScaler:
        def __init__(self):
            pass
        def scale(self, loss):
            return loss
        def unscale_(self, optimizer):
            pass
        def step(self, optimizer):
            optimizer.step()
        def update(self):
            pass

# Helper Functions

def imgtensor2np(img):
    return img.permute(1,2,0).detach().cpu().numpy()
def to_device(args, device):
    args_out = []
    for arg in args:
        if isinstance(arg, list):
            arg = [ elem.to(device) for elem in arg ]
        else:
            arg = arg.to(device)
        args_out.append(arg)
    return args_out


from torch.utils.data import DataLoader
from loss import sequence_loss, EPE, jaccard_index, BCEDiceLoss
from pytorch_ssn.IO import foldercheck
iters = 0

def Optimizer(args, model):
    """ Create the optimizer and learning rate scheduler """
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.wdecay, eps=args.epsilon)
    scheduler = optim.lr_scheduler.OneCycleLR(optimizer, args.lr, args.num_steps+100,
        pct_start=0.05, cycle_momentum=False, anneal_strategy='linear')
    return optimizer, scheduler


def Trainer(args, train_loader, networks, optimizer, scheduler,lossfn, epoch):
    global iters, device

    SSNLayer,flownet, unet = networks
    losses = []
    flownet.eval()
    unet.train()
    iterator = tqdm(enumerate(train_loader), total=len(train_loader), leave=True)
    for i, sample in iterator:
        im1, im2, _, gt2 = to_device(sample[:-2], device)    
        
        # generate flow
        flow_preds = flownet(im1, im2, iters=24, test_mode=True)

        # generate super pixel features
        ssn_input = sample[-2].to(device)  
        ssn_params = to_device(sample[-1], device)
        ssn_params.extend([None])
        slic_features, spix_indices = SSNLayer(ssn_input, ssn_params) 
        slic_features = crop_like(slic_features, im1)
        # spix_indices = connect_segments(spix_indices, ssn_params[0], ssn_params[1], im0.shape[-2], im0.shape[-1])

        seginput = torch.cat((flow_preds[-1], slic_features), dim=1)
        seg_pred = unet(seginput)
        loss = lossfn(seg_pred, gt2)

        iterator.set_description(f'Epoch [{epoch}/{args.epochs}]')
        iterator.set_postfix(BCEloss=loss.item())

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        scheduler.step()
        losses.append(loss.item())
    return np.mean(losses)

def validate(args, val_loader, networks):
    global iters, device

    SSNLayer,flownet, unet = networks
    ious  = []
    # jaccard_index = IoU(num_classes=2)
    with torch.no_grad():
        flownet.eval()
        unet.eval()
        iterator = tqdm(enumerate(val_loader), total=len(val_loader), leave=True)
        for i, sample in iterator:
            im1, im2, _, gt2 = to_device(sample[:-2], device)    
            
            # generate flow
            flow_preds = flownet(im1, im2, iters=24, test_mode=True)

            # generate super pixel features
            ssn_input = sample[-2].to(device)  
            ssn_params = to_device(sample[-1], device)
            ssn_params.extend([None])
            slic_features, _ = SSNLayer(ssn_input, ssn_params) 
            slic_features = crop_like(slic_features, im1)
            # spix_indices = connect_segments(spix_indices, ssn_params[0], ssn_params[1], im0.shape[-2], im0.shape[-1])

            seginput = torch.cat((flow_preds[-1], slic_features), dim=1)
            seg_pred = unet(seginput)
            print(seg_pred[:,0, :, :].shape,gt2[:,0, :, :].shape)
            iou = jaccard_index(seg_pred[:,0, :, :], gt2[:,0, :, :])
            ious.append(iou)
            iterator.set_postfix(JaccardIndex=iou)
        return np.mean(ious)



# [SETUP] - Raft model and SLIC
class MODELARGS:
    def __init__(self):
        self.ssn_dir = './pytorch_ssn/model/slic_model/45000_0.527_model.pt'
        # self.model = "./pytorch_ssn/model/flow_model/raft-kitti.pth"    
        self.model = "./checkpoints/7_tartan.pth"
        self.small= False; self.mixed_precision = True; self.alternate_corr=False; self.dropout = 0.0
        self.validate =False; self.add_noise=True
        self.clip = 1.0; self.gamma = 0.8; self.wdecay = .00005; self.epsilon=1e-8; self.iters=12
        self.batch_size = 6; self.epochs=20; self.lr = 0.00002
args = MODELARGS()
from davisdataloader import DAVISSegmentationLoader
from loss import BCEDiceLoss

lossfn = BCEDiceLoss()

valset = DAVISSegmentationLoader(mode = "val")
trainset = DAVISSegmentationLoader(mode = "train")
val_loader= DataLoader(valset,batch_size=args.batch_size, shuffle=False, num_workers=1)
train_loader= DataLoader(trainset,batch_size=args.batch_size, shuffle=False, num_workers=1)
print(f"Valset has {len(val_loader)} batches")
print(f"Trainset has {len(train_loader)} batches")
args.num_steps = args.epochs * len(train_loader)

SSNLayer = SSN(None, spixel_size=(5,5),dtype = 'layer', device = device)
# flow network
flownet = torch.nn.DataParallel(RAFT(args))
flownet.load_state_dict(torch.load(args.model))
flownet = flownet.module.to(device)
print(f"Flownet size: {flownet.count_parameters()}")

unet = torch.nn.DataParallel(ResUnet())
unet = unet.module.to(device)
print(f"UNet size: {unet.count_parameters()}")

optimizer, scheduler = Optimizer(args, unet)

foldercheck('checkpoints/')
best_iou= -1

for epoch in range(args.epochs):
    train_loss = Trainer(args, train_loader, (SSNLayer,flownet, unet), optimizer, scheduler,lossfn, epoch)
    val_iou = validate(args, val_loader, (SSNLayer,flownet, unet))

    print(f"**** END OF EPOCH: {epoch} || Train loss: {train_loss} || val iou: {val_iou}  **** ")

    if val_iou > best_iou:
        PATH = f'checkpoints/{epoch}_unet.pth' 
        print(f"savng model in {PATH}")
        torch.save(unet.state_dict(), PATH)

