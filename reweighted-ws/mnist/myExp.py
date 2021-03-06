#!/usr/bin/env python 


from __future__ import division

import sys
sys.path.append("../")

import logging
from time import time
import cPickle as pickle

import numpy as np

logger = logging.getLogger()


def run_experiment(args):
    from learning.experiment import Experiment
    from learning.training import Trainer
    from learning.termination import EarlyStopping
    from learning.monitor import MonitorLL, DLogModelParams, SampleFromP
    from learning.monitor.bootstrap import BootstrapLL
    from learning.dataset import MNIST
    from learning.preproc import PermuteColumns, Binarize

    from learning.models.rws  import LayerStack
    from learning.models.sbn  import SBN, SBNTop
    from learning.models.dsbn import DSBN
    from learning.models.darn import DARN, DARNTop
    from learning.models.nade import NADE, NADETop

    np.set_printoptions(precision=2)

    logger.debug("Arguments %s" % args)
    tags = []

    np.random.seed(23)

    # Layer models
    layer_models = {
        "sbn" : (SBN, SBNTop),
        "dsbn": (DSBN, SBNTop),
        "darn": (DARN, DARNTop), 
        "nade": (NADE, NADETop),
    }

    if not args.p_model in layer_models:
        raise "Unknown P-layer model %s" % args.p_model
    p_layer, p_top = layer_models[args.p_model]

    if not args.q_model in layer_models:
        raise "Unknown P-layer model %s" % args.p_model
    q_layer, q_top = layer_models[args.q_model]

    # n_samples to evaluate model
    n_samples_epoch = [1, 5, 25, 100]
    n_samples_final = [1, 5, 10, 25, 100, 500, 1000, 10000, 100000]
    if (args.p_model in ['darn', 'nade']) or (args.q_model in ['darn', 'nade']):
        n_samples_epoch = [1, 5, 25]
        n_samples_final = [1, 5, 10, 25, 100, 500]



    # Layer sizes
    layer_sizes = [int(s) for s in args.layer_sizes.split(",")]

    n_X = 28*28

    p_layers = []
    q_layers = []

    for ls in layer_sizes:
        n_Y = ls
        p_layers.append(
            p_layer(n_X=n_X, n_Y=n_Y)
        )
        q_layers.append(
            q_layer(n_X=n_Y, n_Y=n_X)
        )
        n_X = n_Y
    p_layers.append( p_top(n_X=n_X) )
            

    model = LayerStack(
        p_layers=p_layers,
        q_layers=q_layers
    )
    model.setup()

    # Learning rate
    def lr_tag(value):
        """ Convert a float into a short tag-usable string representation. E.g.:
            0.1   -> 11
            0.01  -> 12
            0.001 -> 13
            0.005 -> 53
        """
        if value == 0.0:
            return "00"
        exp = np.floor(np.log10(value))
        leading = ("%e"%value)[0]
        return "%s%d" % (leading, -exp)

    lr_base = args.lr
    tags += ["lr"+lr_tag(lr_base)]
    lr_p = args.lr_p
    lr_q = args.lr_q
    lr_s = args.lr_s
    if lr_p is None:
        lr_p = lr_base
    else:
        tags += ["lp"+lr_tag(lr_p)]
    if lr_q is None:
        lr_q = lr_base
    else:
        tags += ["lq"+lr_tag(lr_q)]
    if lr_s is None:
        lr_s = lr_base
    else:
        tags += ["ls"+lr_tag(lr_s)]

    # Layer discount
    if args.ldiscount != 1.0:
        tags += ["ldiscount"]

    # LR decay 
    if args.lrdecay != 1.0:
        tags += ["lrdecay"+lr_tag(args.lrdecay-1.)]
    
    # Samples
    n_samples = args.samples
    tags += ["spl%d"%n_samples]

    # Batch size
    batch_size = args.batchsize
    tags += ["bs%d"%batch_size]

    # Sleep interleave
    sleep_interleave = args.sleep_interleave
    tags += ["si%d"%sleep_interleave]

    # Dataset
    if args.shuffle:
        np.random.seed(23)
        preproc = [PermuteColumns()]
        tags += ["shuffle"]
    else:
        preproc = []

    if args.rebinarize:
        binarize_preproc = preproc + [Binarize(late=True)]
        dataset = MNIST(which_set='train', preproc=binarize_preproc, n_datapoints=50000)
        valiset = MNIST(which_set='valid', preproc=binarize_preproc, n_datapoints=10000)
        testset = MNIST(fname="mnist_salakhutdinov.pkl.gz", which_set='test', preproc=preproc, n_datapoints=10000)
        tags += ["rb"]
    else:
        dataset = MNIST(fname="mnist_salakhutdinov.pkl.gz", which_set='train', preproc=preproc, n_datapoints=50000)
        valiset = MNIST(fname="mnist_salakhutdinov.pkl.gz", which_set='valid', preproc=preproc, n_datapoints=10000)
        testset = MNIST(fname="mnist_salakhutdinov.pkl.gz", which_set='test', preproc=preproc, n_datapoints=10000)

    print "train size:", dataset.X.shape, dataset.Y.shape
    print "valiset:", valiset.X.shape, valiset.Y.shape
    print "testset:", testset.X.shape, testset.Y.shape

    return

    if args.lookahead != 10:
        tags += ["lah%d" % args.lookahead]

    tags.sort()
    expname = "%s-%s-%s-%s"% ("-".join(tags), args.p_model, args.q_model, "-".join([str(s) for s in layer_sizes]))

    logger.info("Running %s" % expname)

    
    trainer = Trainer(
        batch_size=batch_size,
        n_samples=n_samples,
        sleep_interleave=sleep_interleave,
        learning_rate_p=lr_p,
        learning_rate_q=lr_q,
        learning_rate_s=lr_s,
        layer_discount=args.ldiscount,
        lr_decay=args.lrdecay,
        dataset=dataset, 
        model=model,
        termination=EarlyStopping(lookahead=args.lookahead, min_epochs=10),
        epoch_monitors=[
            DLogModelParams(), 
            SampleFromP(n_samples=100),
            MonitorLL(name="valiset", data=valiset, n_samples=n_samples_epoch),
        ],
        final_monitors=[
            MonitorLL(name="final-valiset", data=valiset, n_samples=n_samples_final),
            MonitorLL(name="final-testset", data=testset, n_samples=n_samples_final),
        ],
    )

    experiment = Experiment()
    experiment.trainer = trainer
    experiment.setup_output_dir(expname)
    experiment.print_summary()
    experiment.setup_logging()

    if args.cont is None:
        experiment.run_experiment()
    else:
        logger.info("Continuing experiment %s ...." % args.cont)
        experiment.continue_experiment(args.cont+"/results.h5", row=-1)
 
    logger.info("Finished. Wrinting metadata")

    experiment.print_summary()

#=============================================================================
if __name__ == "__main__":
    import argparse 

    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', '-v', action='count')
    parser.add_argument('--shuffle', action='store_true', default=False)
    parser.add_argument('--cont', nargs='?', default=None,
        help="Continue a previous in result_dir")
    parser.add_argument('--samples', default=10, type=int, 
        help="Number of training samples (default: 10)")
    parser.add_argument('--batchsize', default=100, type=int, 
        help="Mini batch size (default: 100)")
    parser.add_argument('--sleep-interleave', '--si', default=2, type=int, 
        help="Sleep interleave (default: 2)")
    parser.add_argument('--lr', default=1e-3, type=float, help="Learning rate (default: 1e-3)")
    parser.add_argument('--lr_p', default=None, type=float, help="p learning rate")
    parser.add_argument('--lr_q', default=None, type=float, help="wake-q-learing rate")
    parser.add_argument('--lr_s', default=None, type=float, help="sleep-q-learning rate")
    parser.add_argument('--lrdecay', default=1., type=float, help="learning rate decay")
    parser.add_argument('--ldiscount', default=1., type=float, help="layer_discount")
    parser.add_argument('--rebinarize', default=False, action="store_true", 
        help="Resample binary MNIST from orig. dataset during training");
    parser.add_argument('--lookahead', default=10, type=int, 
        help="Termination criteria: # epochs without LL increase")
    parser.add_argument('p_model', default="SBN", 
        help="SBN, DARN or NADE (default: SBN")
    parser.add_argument('q_model', default="SBN",
        help="SBN, DARN or NADE (default: SBN")
    parser.add_argument('layer_sizes', default="200,200,10", 
        help="Comma seperated list of sizes. Layer closest to the data comes first")
    args = parser.parse_args()

    FORMAT = '[%(asctime)s] %(name)-15s %(message)s'
    DATEFMT = "%H:%M:%S"
    logging.basicConfig(format=FORMAT, datefmt=DATEFMT, level=logging.INFO)

    run_experiment(args)
